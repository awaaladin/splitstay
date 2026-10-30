package com.splitpay.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.splitpay.app.data.BANKS
import com.splitpay.app.data.BankAccount
import com.splitpay.app.data.BankAccountInput
import com.splitpay.app.data.Notification
import com.splitpay.app.data.ProfileUpdate
import com.splitpay.app.data.Session
import com.splitpay.app.data.SplitPayApi
import com.splitpay.app.data.userMessage
import kotlinx.coroutines.launch
import retrofit2.HttpException

@Composable
fun NotificationsScreen(api: SplitPayApi, padding: PaddingValues, onOpenGroup: (Int) -> Unit) {
    val loader = rememberLoader { api.notifications().results }
    val scope = rememberCoroutineScope()
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { list ->
            if (list.isEmpty()) {
                Box(Modifier.fillMaxSize().padding(24.dp)) { Text("Nothing here yet.") }
            } else {
                LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    item {
                        TextButton(onClick = {
                            scope.launch { runCatching { api.markAllRead() }; loader.reload() }
                        }) { Text("Mark all as read") }
                    }
                    items(list, key = { it.id }) { item ->
                        NotificationRow(item) {
                            scope.launch { runCatching { api.markRead(item.id) } }
                            item.group?.let(onOpenGroup)
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificationRow(item: Notification, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 10.dp)) {
        Text(item.title, fontWeight = if (item.isRead) FontWeight.Normal else FontWeight.SemiBold)
        if (item.body.isNotBlank()) Text(item.body, style = MaterialTheme.typography.bodyMedium)
        Text(prettyDateTime(item.createdAt), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun AccountScreen(api: SplitPayApi, session: Session, padding: PaddingValues) {
    val loader = rememberLoader {
        val account = try {
            api.bankAccount()
        } catch (e: HttpException) {
            if (e.code() == 404) null else throw e
        }
        api.me() to account
    }
    val scope = rememberCoroutineScope()
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { (profile, account) ->
            var name by remember(profile) { mutableStateOf(profile.fullName) }
            var phone by remember(profile) { mutableStateOf(profile.phoneNumber.orEmpty()) }
            var busy by remember { mutableStateOf(false) }
            var error by remember { mutableStateOf<String?>(null) }
            var notice by remember { mutableStateOf<String?>(null) }
            Column(
                Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(profile.email, style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(name, { name = it }, label = { Text("Full name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(
                    phone, { phone = it }, label = { Text("Phone number") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier.fillMaxWidth(),
                )
                ErrorText(error)
                notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
                BusyButton("Save profile", busy, enabled = name.isNotBlank()) {
                    scope.launch {
                        busy = true
                        error = null
                        notice = null
                        try {
                            api.updateMe(ProfileUpdate(name.trim(), phone.trim()))
                            notice = "Saved."
                        } catch (e: kotlinx.coroutines.CancellationException) {
                            throw e
                        } catch (e: Exception) {
                            error = e.userMessage()
                        } finally {
                            busy = false
                        }
                    }
                }
                HorizontalDivider()
                BankSection(api, account, loader::reload)
                HorizontalDivider()
                OutlinedButton(onClick = session::clear, modifier = Modifier.fillMaxWidth()) { Text("Sign out") }
            }
        }
    }
}

@Composable
private fun BankSection(api: SplitPayApi, account: BankAccount?, onChanged: () -> Unit) {
    var editing by remember(account) { mutableStateOf(account == null) }
    var bank by remember(account) { mutableStateOf(account?.bankCode.orEmpty()) }
    var number by remember(account) { mutableStateOf("") }
    var holder by remember(account) { mutableStateOf(account?.accountName.orEmpty()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Text("Bank account", style = MaterialTheme.typography.titleMedium)
    if (!editing && account != null) {
        LabelValue(account.bankName, account.maskedNumber)
        LabelValue("Name", account.accountName)
        OutlinedButton(onClick = { editing = true }, modifier = Modifier.fillMaxWidth()) { Text("Change") }
        return
    }
    Picker("Bank", BANKS, bank) { bank = it }
    OutlinedTextField(
        number, { value -> number = value.filter(Char::isDigit).take(10) },
        label = { Text("Account number") }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(holder, { holder = it }, label = { Text("Account name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
    ErrorText(error)
    BusyButton("Save bank account", busy, enabled = bank.isNotBlank() && number.length == 10 && holder.isNotBlank()) {
        scope.launch {
            busy = true
            error = null
            try {
                api.saveBankAccount(BankAccountInput(bank, BANKS.first { it.first == bank }.second, holder.trim(), number))
                onChanged()
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                error = e.userMessage()
            } finally {
                busy = false
            }
        }
    }
}

/** The bell's count: refreshed whenever the screen it sits on is shown. */
@Composable
fun rememberUnreadCount(api: SplitPayApi, key: Any?): Int {
    var unread by remember { mutableStateOf(0) }
    LaunchedEffect(key) {
        runCatching { api.unreadCount().unread }.onSuccess { unread = it }
    }
    return unread
}
