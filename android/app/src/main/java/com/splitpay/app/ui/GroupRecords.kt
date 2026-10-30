package com.splitpay.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.splitpay.app.data.LedgerEntry
import com.splitpay.app.data.SplitPayApi
import kotlinx.serialization.json.JsonPrimitive

@Composable
fun EntryRow(entry: LedgerEntry) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Column(Modifier.weight(1f)) {
            Text(entry.title)
            Text(
                listOf(entry.actor, prettyDateTime(entry.at)).filter { it.isNotBlank() }.joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if ((entry.detail["needs_review"] as? JsonPrimitive)?.content == "true") {
                Text("Flagged for admin review.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
        entry.amount?.let { Text(money(it)) }
    }
}

@Composable
fun LedgerScreen(api: SplitPayApi, groupId: Int, padding: PaddingValues) {
    val loader = rememberLoader(groupId) { api.group(groupId) to api.ledger(groupId) }
    var onlyMine by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { (group, ledger) ->
            val me = group.myMembership?.user?.name
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text(group.name, style = MaterialTheme.typography.titleLarge)
                ledger.summary?.let { summary ->
                    LabelValue("Raised", money(summary.funded))
                    LabelValue("Remaining", money(summary.remaining))
                    summary.fee?.let { LabelValue("Service fees", money(it)) }
                    summary.net?.let { LabelValue("Paid out", money(it)) }
                }
                HorizontalDivider()
                Text("Members", style = MaterialTheme.typography.titleMedium)
                ledger.members.forEach { LabelValue(it.name, "${money(it.paid)} of ${money(it.share)}") }
                HorizontalDivider()
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(!onlyMine, { onlyMine = false }, { Text("Everyone") })
                    FilterChip(onlyMine, { onlyMine = true }, { Text("Just me") })
                }
                val entries = if (onlyMine) ledger.results.filter { it.actor == me } else ledger.results
                if (entries.isEmpty()) Text("Nothing here yet.")
                entries.forEach { EntryRow(it) }
            }
        }
    }
}

@Composable
fun ReceiptScreen(api: SplitPayApi, groupId: Int, padding: PaddingValues) {
    val loader = rememberLoader(groupId) {
        val group = api.group(groupId)
        Triple(group, loadRecord(api, group), api.contributions(groupId).results.filter { it.status == "paid" })
    }
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { (group, record, paid) ->
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (record == null) {
                    Text("There's no receipt for this group yet.")
                    return@Column
                }
                val isBill = group.payoutType == "bill_payment"
                Text(if (isBill) "Bill payment receipt" else "Bank transfer receipt", style = MaterialTheme.typography.titleLarge)
                if (record.status != "completed") {
                    Text(statusLabel(record.status))
                    if (record.failureReason.isNotBlank()) ErrorText(record.failureReason)
                    return@Column
                }
                Text("Paid ${record.completedAt?.let(::prettyDateTime).orEmpty()}", color = MaterialTheme.colorScheme.primary)
                LabelValue("Group", group.name)
                if (isBill) {
                    LabelValue("Paid to", record.biller)
                    LabelValue("Meter", "${record.customerId} (${record.variation.ifBlank { "prepaid" }})")
                    if (record.customerName.isNotBlank()) LabelValue("Customer", record.customerName)
                } else {
                    LabelValue("Paid to", record.recipientAccountName)
                    LabelValue("Account", "${record.recipientBankName} ${record.recipientAccount}")
                }
                LabelValue("Reference", record.reference)
                if (record.providerReference.isNotBlank()) LabelValue("Biller reference", record.providerReference)
                if (record.token.isNotBlank()) {
                    HorizontalDivider()
                    Text(listOf("Electricity token", record.units).filter { it.isNotBlank() }.joinToString(" · "))
                    Text(record.token, style = MaterialTheme.typography.titleMedium)
                    OutlinedButton(onClick = { clipboard.setText(AnnotatedString(record.token)); copied = true }) {
                        Text(if (copied) "Copied" else "Copy token")
                    }
                }
                HorizontalDivider()
                Text("Contributions (${paid.size})", style = MaterialTheme.typography.titleMedium)
                paid.forEach { LabelValue(it.member?.name.orEmpty(), money(it.amount)) }
                HorizontalDivider()
                LabelValue("Pooled by members", money(record.grossAmount))
                record.fees.forEach { LabelValue(it.description, "-${money(it.amount)}") }
                LabelValue(if (isBill) "Amount paid to biller" else "Amount paid", money(record.netAmount))
                val onTop = paid.fold(java.math.BigDecimal.ZERO) { sum, c -> sum + c.serviceFee.decimal() }
                if (onTop.signum() > 0) {
                    Text("Members also paid ${money(onTop.toPlainString())} in SplitPay service fees on top of their shares.", style = MaterialTheme.typography.bodySmall)
                }
                if (record.isPartial) {
                    Text("Paid out early at the admin's request, before the ${money(group.targetAmount)} target was reached.", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
