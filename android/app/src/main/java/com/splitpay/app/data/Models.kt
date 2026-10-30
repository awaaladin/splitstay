package com.splitpay.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Money stays a String (the API sends decimals as strings) so nothing is rounded through a Double.

@Serializable
data class LoginRequest(val identifier: String, val password: String)

@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    @SerialName("full_name") val fullName: String,
    @SerialName("phone_number") val phoneNumber: String,
)

@Serializable
data class TokenPair(val refresh: String, val access: String)

@Serializable
data class RefreshRequest(val refresh: String)

@Serializable
data class AccessToken(val access: String)

@Serializable
data class Profile(
    val id: Int,
    val email: String,
    @SerialName("full_name") val fullName: String = "",
    @SerialName("phone_number") val phoneNumber: String? = null,
)

@Serializable
data class ProfileUpdate(
    @SerialName("full_name") val fullName: String,
    @SerialName("phone_number") val phoneNumber: String,
)

@Serializable
data class BankAccount(
    @SerialName("bank_code") val bankCode: String,
    @SerialName("bank_name") val bankName: String,
    @SerialName("account_name") val accountName: String,
    @SerialName("masked_number") val maskedNumber: String = "",
)

@Serializable
data class BankAccountInput(
    @SerialName("bank_code") val bankCode: String,
    @SerialName("bank_name") val bankName: String,
    @SerialName("account_name") val accountName: String,
    @SerialName("account_number") val accountNumber: String,
)

@Serializable
data class UserSummary(val id: Int, val email: String, val name: String)

@Serializable
data class Progress(
    val target: String,
    val funded: String,
    val remaining: String,
    val percent: String,
    @SerialName("is_funded") val isFunded: Boolean,
)

@Serializable
data class Membership(
    val user: UserSummary,
    @SerialName("contribution_share") val share: String,
    val status: String,
    @SerialName("amount_paid") val amountPaid: String,
    val outstanding: String,
)

@Serializable
data class Group(
    val id: Int,
    val name: String,
    val description: String = "",
    val purpose: String,
    @SerialName("target_amount") val targetAmount: String,
    @SerialName("due_date") val dueDate: String,
    @SerialName("is_recurring") val isRecurring: Boolean = false,
    val status: String,
    val admin: UserSummary,
    @SerialName("payout_type") val payoutType: String,
    @SerialName("allow_partial_payout") val allowPartialPayout: Boolean = false,
    @SerialName("recipient_bank_name") val recipientBankName: String = "",
    @SerialName("recipient_account_name") val recipientAccountName: String = "",
    @SerialName("recipient_account") val recipientAccount: String = "",
    @SerialName("biller_name") val billerName: String = "",
    val progress: Progress,
    @SerialName("my_membership") val myMembership: Membership? = null,
)

@Serializable
data class Page<T>(val count: Int = 0, val next: String? = null, val results: List<T> = emptyList())

@Serializable
data class MemberInput(val identifier: String)

@Serializable
data class GroupInput(
    val name: String,
    val description: String,
    val purpose: String,
    @SerialName("target_amount") val targetAmount: String,
    @SerialName("due_date") val dueDate: String,
    @SerialName("payout_type") val payoutType: String = "bank_transfer",
    @SerialName("allow_partial_payout") val allowPartialPayout: Boolean,
    @SerialName("recipient_bank_code") val recipientBankCode: String,
    @SerialName("recipient_bank_name") val recipientBankName: String,
    @SerialName("recipient_account_name") val recipientAccountName: String,
    @SerialName("recipient_account_number") val recipientAccountNumber: String,
    val members: List<MemberInput>,
)

@Serializable
class ContributeRequest

@Serializable
data class Contribution(
    val id: Int,
    val amount: String,
    @SerialName("service_fee") val serviceFee: String,
    @SerialName("charge_amount") val chargeAmount: String,
    val status: String,
    val reference: String,
)

@Serializable
data class ContributeResponse(
    val contribution: Contribution,
    @SerialName("checkout_url") val checkoutUrl: String,
)

@Serializable
data class LedgerEntry(
    val at: String,
    val kind: String,
    val title: String,
    val amount: String? = null,
    val status: String = "",
    val actor: String = "",
)

@Serializable
data class MemberStanding(
    @SerialName("user_id") val userId: Int,
    val name: String,
    val share: String,
    val paid: String,
    val outstanding: String,
    val state: String,
)

@Serializable
data class Ledger(
    val results: List<LedgerEntry> = emptyList(),
    val members: List<MemberStanding> = emptyList(),
)

@Serializable
data class Notification(
    val id: Int,
    val title: String,
    val body: String = "",
    val group: Int? = null,
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class UnreadCount(val unread: Int)
