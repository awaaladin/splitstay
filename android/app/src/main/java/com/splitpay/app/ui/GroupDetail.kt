package com.splitpay.app.ui

import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.splitpay.app.data.ContributeRequest
import com.splitpay.app.data.ContributeResponse
import com.splitpay.app.data.Group
import com.splitpay.app.data.Ledger
import com.splitpay.app.data.MemberStanding
import com.splitpay.app.data.PayoutRecord
import com.splitpay.app.data.SplitPayApi
import com.splitpay.app.data.userMessage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import retrofit2.HttpException
import retrofit2.Response

private const val LIVE_REFRESH_MS = 8_000L

data class GroupPage(val group: Group, val ledger: Ledger?, val record: PayoutRecord?)

suspend fun loadRecord(api: SplitPayApi, group: Group): PayoutRecord? =
    if (group.payoutType == "bill_payment") {
        api.billPayments(group.id).results.firstOrNull()
    } else {
        api.payouts(group.id).results.firstOrNull()
    }

private fun Response<Unit>.orThrow() {
    if (!isSuccessful) throw HttpException(this)
}

private sealed class Confirm(val title: String, val body: String) {
    data object Leave : Confirm("Decline this invitation?", "You won't be part of this group.")
    data object Cancel : Confirm("Cancel this group?", "This can't be undone.")
    data class Payout(val amount: String) : Confirm(
        "Pay out before the target is reached?",
        "Only $amount will be paid out, and the group closes. This can't be undone.",
    )
    data class Remove(val member: MemberStanding) : Confirm("Remove ${member.name}?", "Shares will be rebalanced.")
}

@Composable
fun GroupDetailScreen(
    api: SplitPayApi, groupId: Int, padding: PaddingValues,
    onLeft: () -> Unit, onEdit: () -> Unit, onLedger: () -> Unit, onReceipt: () -> Unit,
) {
    val loader = rememberLoader(groupId) {
        val group = api.group(groupId)
        // Invited members can't read the history yet.
        val joined = group.myMembership?.status == "joined"
        GroupPage(
            group,
            if (joined) api.ledger(groupId) else null,
            if (joined) loadRecord(api, group) else null,
        )
    }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var quote by remember { mutableStateOf<ContributeResponse?>(null) }
    var pending by rememberSaveable { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf<Confirm?>(null) }
    var inviting by remember { mutableStateOf(false) }
    var sharing by remember { mutableStateOf<MemberStanding?>(null) }

    fun act(block: suspend () -> Unit) {
        scope.launch {
            busy = true
            error = null
            try {
                block()
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                error = e.userMessage()
            } finally {
                busy = false
            }
        }
    }

    // Like the website's group page, this keeps the pot and members current while it's open.
    LaunchedEffect(groupId) {
        while (true) {
            delay(LIVE_REFRESH_MS)
            val status = loader.data?.group?.status
            if (status != "paid_out" && status != "cancelled") loader.reload()
        }
    }

    ReloadOnResume {
        val reference = pending
        if (reference != null) {
            pending = null
            act {
                val result = api.verify(reference)
                notice = when (result.status) {
                    "paid" -> "Payment received. Thank you."
                    "failed" -> "That payment didn't go through."
                    else -> "Your payment hasn't been confirmed yet. If you paid, it will show here shortly."
                }
                loader.reload()
            }
        } else {
            loader.reload()
        }
    }

    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { page ->
            val group = page.group
            val record = page.record
            val mine = group.myMembership
            val isOpen = group.status == "open" || group.status == "overdue"
            val isAdmin = mine != null && mine.user.id == group.admin.id
            val invited = mine?.status == "invited" && !isAdmin
            val noMoneyYet = group.progress.funded.decimal().signum() == 0
            val canManage = isAdmin && isOpen && noMoneyYet
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(group.name, style = MaterialTheme.typography.headlineSmall)
                if (group.description.isNotBlank()) Text(group.description)
                LinearProgressIndicator(
                    progress = { (group.progress.percent.toFloatOrNull() ?: 0f) / 100f },
                    modifier = Modifier.fillMaxWidth(),
                )
                LabelValue("Raised", "${money(group.progress.funded)} of ${money(group.progress.target)}")
                LabelValue("Status", statusLabel(group.status))
                LabelValue("Due", prettyDate(group.dueDate))
                LabelValue("Admin", group.admin.name)
                if (group.isRecurring) LabelValue("Repeats", "${statusLabel(group.recurrenceInterval.orEmpty())}, cycle ${group.cycleNumber}")
                if (group.payoutType == "bank_transfer") {
                    LabelValue("Paid to", group.recipientAccountName)
                    LabelValue("Account", "${group.recipientBankName} ${group.recipientAccount}".trim())
                } else {
                    LabelValue("Paid to", group.billerName)
                    LabelValue("Meter", group.billCustomerId)
                }

                notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
                ErrorText(error)

                if (mine != null && !invited) {
                    HorizontalDivider()
                    Text("Your part", style = MaterialTheme.typography.titleMedium)
                    LabelValue("Your share", money(mine.share))
                    LabelValue("You've paid", money(mine.amountPaid))
                    LabelValue("Outstanding", money(mine.outstanding))
                    group.payQuote?.let { q ->
                        HorizontalDivider()
                        LabelValue("Your share (goes to the group)", money(q.share))
                        LabelValue("SplitPay service fee", money(q.fee))
                        LabelValue("You pay today", money(q.total))
                        BusyButton("Pay ${money(q.total)}", busy) {
                            act { quote = api.contribute(groupId, ContributeRequest()) }
                        }
                    }
                    if (group.payQuote == null && mine.share.decimal().signum() > 0 && mine.outstanding.decimal().signum() == 0) {
                        Text("Your share is paid in full.", color = MaterialTheme.colorScheme.primary)
                    }
                }
                if (invited) {
                    HorizontalDivider()
                    LabelValue("Your share", money(mine?.share))
                    if (isOpen) {
                        BusyButton("Accept invitation", busy) { act { api.accept(groupId); loader.reload() } }
                        OutlinedButton(onClick = { confirm = Confirm.Leave }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Decline") }
                    }
                }

                if (record != null) {
                    HorizontalDivider()
                    Text(if (group.payoutType == "bill_payment") "Bill payment" else "Bank transfer", style = MaterialTheme.typography.titleMedium)
                    Text(statusLabel(record.status))
                    when (record.status) {
                        "completed" -> OutlinedButton(onClick = onReceipt, modifier = Modifier.fillMaxWidth()) { Text("View receipt") }
                        "failed" -> {
                            ErrorText(record.failureReason.ifBlank { "The payment could not be completed." })
                            if (isAdmin) {
                                BusyButton("Retry payment", busy) {
                                    act { api.payout(groupId).orThrow(); notice = "Retrying the payment now."; loader.reload() }
                                }
                            } else {
                                Text("The group admin can retry this.")
                            }
                        }
                        else -> Text("The payment is in progress. This page updates on its own.")
                    }
                }

                if (isAdmin && group.allowPartialPayout && isOpen && !noMoneyYet && record == null) {
                    OutlinedButton(
                        onClick = { confirm = Confirm.Payout(money(group.progress.funded)) }, enabled = !busy,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Pay out ${money(group.progress.funded)} now") }
                }
                if (group.needsReview) {
                    ErrorText("One or more payments arrived in an unusual state and need review. Check the ledger.")
                }

                page.ledger?.let { ledger ->
                    HorizontalDivider()
                    Text("Members", style = MaterialTheme.typography.titleMedium)
                    ledger.members.forEach { member ->
                        LabelValue(member.name, "${money(member.paid)} of ${money(member.share)}")
                        if (canManage && member.userId != group.admin.id) {
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                                TextButton(onClick = { sharing = member }, enabled = !busy) { Text("Set share") }
                                TextButton(onClick = { confirm = Confirm.Remove(member) }, enabled = !busy) { Text("Remove") }
                            }
                        } else if (canManage) {
                            TextButton(onClick = { sharing = member }, enabled = !busy) { Text("Set share") }
                        }
                    }
                    if (canManage) {
                        OutlinedButton(onClick = { inviting = true }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Invite a member") }
                    }
                    HorizontalDivider()
                    Text("Recent activity", style = MaterialTheme.typography.titleMedium)
                    ledger.results.take(10).forEach { EntryRow(it) }
                    TextButton(onClick = onLedger) { Text("Full ledger") }
                }

                if (isAdmin && isOpen) {
                    HorizontalDivider()
                    OutlinedButton(onClick = onEdit, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Edit group") }
                }
                if (isAdmin && isOpen && noMoneyYet) {
                    TextButton(onClick = { confirm = Confirm.Cancel }, enabled = !busy) { Text("Cancel group") }
                }
            }

            quote?.let { q ->
                AlertDialog(
                    onDismissRequest = { quote = null },
                    title = { Text("Confirm payment") },
                    text = {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            LabelValue("Your share", money(q.contribution.amount))
                            LabelValue("Service fee", money(q.contribution.serviceFee))
                            HorizontalDivider()
                            LabelValue("You pay", money(q.contribution.chargeAmount))
                        }
                    },
                    confirmButton = {
                        TextButton(onClick = {
                            pending = q.contribution.reference
                            quote = null
                            notice = null
                            CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(q.checkoutUrl))
                        }) { Text("Continue to Paystack") }
                    },
                    dismissButton = { TextButton(onClick = { quote = null }) { Text("Not now") } },
                )
            }

            confirm?.let { action ->
                AlertDialog(
                    onDismissRequest = { confirm = null },
                    title = { Text(action.title) },
                    text = { Text(action.body) },
                    confirmButton = {
                        TextButton(onClick = {
                            confirm = null
                            act {
                                when (action) {
                                    Confirm.Leave -> { api.leave(groupId).orThrow(); onLeft() }
                                    Confirm.Cancel -> { api.cancel(groupId); loader.reload() }
                                    is Confirm.Payout -> {
                                        api.payout(groupId).orThrow()
                                        notice = "Payout started. You'll be notified when it completes."
                                        loader.reload()
                                    }
                                    is Confirm.Remove -> { api.removeMember(groupId, action.member.userId).orThrow(); loader.reload() }
                                }
                            }
                        }) { Text("Yes") }
                    },
                    dismissButton = { TextButton(onClick = { confirm = null }) { Text("Keep as it is") } },
                )
            }

            if (inviting) {
                var who by remember { mutableStateOf("") }
                var share by remember { mutableStateOf("") }
                AlertDialog(
                    onDismissRequest = { inviting = false },
                    title = { Text("Invite a member") },
                    text = {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(who, { who = it }, label = { Text("Email or phone number") }, singleLine = true)
                            AmountField("Custom share (₦, optional)", share) { share = it }
                        }
                    },
                    confirmButton = {
                        TextButton(enabled = who.isNotBlank(), onClick = {
                            val body = buildJsonObject {
                                put("identifier", who.trim())
                                if (share.isNotBlank()) put("contribution_share", share)
                            }
                            inviting = false
                            act { api.addMember(groupId, body); loader.reload() }
                        }) { Text("Invite") }
                    },
                    dismissButton = { TextButton(onClick = { inviting = false }) { Text("Close") } },
                )
            }

            sharing?.let { member ->
                var share by remember(member) { mutableStateOf("") }
                AlertDialog(
                    onDismissRequest = { sharing = null },
                    title = { Text("Share for ${member.name}") },
                    text = { AmountField("Amount (₦). Empty splits equally", share) { share = it } },
                    confirmButton = {
                        TextButton(onClick = {
                            val value = if (share.isBlank()) JsonNull else JsonPrimitive(share)
                            val body = kotlinx.serialization.json.JsonObject(mapOf("contribution_share" to value))
                            sharing = null
                            act { api.setShare(groupId, member.userId, body); loader.reload() }
                        }) { Text("Save") }
                    },
                    dismissButton = { TextButton(onClick = { sharing = null }) { Text("Close") } },
                )
            }
        }
    }
}

@Composable
fun AmountField(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value, { typed -> onChange(typed.filter { it.isDigit() || it == '.' }) },
        label = { Text(label) }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        modifier = Modifier.fillMaxWidth(),
    )
}
