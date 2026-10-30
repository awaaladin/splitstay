package com.splitpay.app.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import com.splitpay.app.BuildConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import java.io.IOException
import java.util.concurrent.TimeUnit

interface SplitPayApi {
    @POST("auth/token/") suspend fun login(@Body body: LoginRequest): TokenPair
    @POST("auth/register/") suspend fun register(@Body body: RegisterRequest): TokenPair
    @GET("auth/me/") suspend fun me(): Profile
    @PATCH("auth/me/") suspend fun updateMe(@Body body: ProfileUpdate): Profile
    @GET("auth/me/bank-account/") suspend fun bankAccount(): BankAccount
    @PUT("auth/me/bank-account/") suspend fun saveBankAccount(@Body body: BankAccountInput): BankAccount
    @DELETE("auth/me/bank-account/") suspend fun deleteBankAccount(): retrofit2.Response<Unit>

    @GET("groups/?page_size=100") suspend fun groups(): Page<Group>
    @POST("groups/") suspend fun createGroup(@Body body: GroupInput): Group
    @GET("groups/{id}/") suspend fun group(@Path("id") id: Int): Group
    @POST("groups/{id}/accept/") suspend fun accept(@Path("id") id: Int): Group
    @POST("groups/{id}/leave/") suspend fun leave(@Path("id") id: Int): retrofit2.Response<Unit>
    @POST("groups/{id}/cancel/") suspend fun cancel(@Path("id") id: Int): Group
    @POST("groups/{id}/members/") suspend fun addMember(@Path("id") id: Int, @Body body: MemberInput): Membership
    @POST("groups/{id}/contribute/") suspend fun contribute(@Path("id") id: Int, @Body body: ContributeRequest): ContributeResponse
    @POST("groups/{id}/payout/") suspend fun payout(@Path("id") id: Int): retrofit2.Response<Unit>
    @GET("groups/{id}/ledger/") suspend fun ledger(@Path("id") id: Int): Ledger

    @POST("payments/verify/{reference}/") suspend fun verify(@Path("reference") reference: String): Contribution

    @GET("notifications/?page_size=100") suspend fun notifications(): Page<Notification>
    @GET("notifications/unread-count/") suspend fun unreadCount(): UnreadCount
    @POST("notifications/{id}/read/") suspend fun markRead(@Path("id") id: Int): Notification
    @POST("notifications/read-all/") suspend fun markAllRead(): retrofit2.Response<Unit>
}

/** The JWT pair, encrypted at rest. `signedIn` drives the top-level navigation. */
class Session(context: Context) {
    private val prefs: SharedPreferences = EncryptedSharedPreferences.create(
        context,
        "session",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    private val _signedIn = MutableStateFlow(prefs.contains(REFRESH))
    val signedIn: StateFlow<Boolean> = _signedIn

    val access: String? get() = prefs.getString(ACCESS, null)
    val refresh: String? get() = prefs.getString(REFRESH, null)

    fun save(tokens: TokenPair) {
        prefs.edit().putString(ACCESS, tokens.access).putString(REFRESH, tokens.refresh).apply()
        _signedIn.value = true
    }

    fun saveAccess(token: String) {
        prefs.edit().putString(ACCESS, token).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
        _signedIn.value = false
    }

    private companion object {
        const val ACCESS = "access"
        const val REFRESH = "refresh"
    }
}

private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

fun buildApi(session: Session): SplitPayApi {
    val contentType = "application/json".toMediaType()
    val converter = json.asConverterFactory(contentType)
    val base = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS) // Serverless cold starts can take several seconds.
        .readTimeout(45, TimeUnit.SECONDS)
        .build()

    val refresher = Retrofit.Builder().baseUrl(BuildConfig.API_BASE_URL).client(base)
        .addConverterFactory(converter).build().create(RefreshApi::class.java)

    val client = base.newBuilder()
        .addInterceptor(Interceptor { chain ->
            val token = session.access
            val request = if (token != null) {
                chain.request().newBuilder().header("Authorization", "Bearer $token").build()
            } else {
                chain.request()
            }
            chain.proceed(request)
        })
        .authenticator(TokenAuthenticator(session, refresher))
        .build()

    return Retrofit.Builder().baseUrl(BuildConfig.API_BASE_URL).client(client)
        .addConverterFactory(converter).build().create(SplitPayApi::class.java)
}

private interface RefreshApi {
    @POST("auth/token/refresh/") fun refresh(@Body body: RefreshRequest): retrofit2.Call<AccessToken>
}

/** On a 401, swaps the refresh token for a new access token once; a dead refresh token signs out. */
private class TokenAuthenticator(private val session: Session, private val api: RefreshApi) : Authenticator {
    @Synchronized
    override fun authenticate(route: Route?, response: Response): Request? {
        val refresh = session.refresh ?: return null
        if (response.priorResponse != null) return null
        val sent = response.request.header("Authorization")
        val current = session.access
        if (current != null && sent != "Bearer $current") {
            return response.request.newBuilder().header("Authorization", "Bearer $current").build()
        }
        val result = try {
            api.refresh(RefreshRequest(refresh)).execute()
        } catch (e: IOException) {
            return null // Offline is not a reason to sign out.
        }
        val token = result.body()?.access
        if (token == null) {
            if (result.code() == 400 || result.code() == 401) session.clear()
            return null
        }
        session.saveAccess(token)
        return response.request.newBuilder().header("Authorization", "Bearer $token").build()
    }
}

/** A sentence for the screen, from whatever shape DRF sent: detail, field errors, or a bare list. */
fun Throwable.userMessage(): String = when (this) {
    is HttpException -> {
        val body = try { response()?.errorBody()?.string() } catch (e: IOException) { null }
        val parsed = body?.let { runCatching { json.parseToJsonElement(it) }.getOrNull() }
        parsed?.let(::firstMessage)
            ?: if (code() >= 500) "SplitPay is having trouble. Try again shortly." else "That didn't work. Try again."
    }
    is IOException -> "Couldn't reach SplitPay. Check your connection and try again."
    else -> "Something went wrong. Try again."
}

private fun firstMessage(element: JsonElement): String? = when (element) {
    is JsonPrimitive -> element.content
    is JsonArray -> element.firstNotNullOfOrNull(::firstMessage)
    is JsonObject -> element["detail"]?.let(::firstMessage)
        ?: element.values.firstNotNullOfOrNull(::firstMessage)
}
