package com.splitpay.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.splitpay.app.data.BANKS
import com.splitpay.app.data.Biller
import com.splitpay.app.data.Group
import com.splitpay.app.data.PURPOSES
import com.splitpay.app.data.SplitPayApi
import com.splitpay.app.data.userMessage
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

private val INTERVALS = listOf("monthly" to "Monthly", "quarterly" to "Quarterly", "annual" to "Annual")
private val METER_TYPES = listOf("prepaid" to "Prepaid", "postpaid" to "Postpaid")
private val PAYOUT_TYPES = listOf("bank_transfer" to "Bank transfer", "bill_payment" to "Pay a bill")

private data class FormSetup(val group: Group?, val billers: List<Biller>)
private data class MemberRow(val identifier: String, val share: String)

/** Creates a group, or edits one when `groupId` is given. Calls `onSaved` with the group's id. */
@Composable
fun GroupFormScreen(api: SplitPayApi, padding: PaddingValues, groupId: Int?, onSaved: (Int) -> Unit) {
    val loader = rememberLoader(groupId) {
        val billers = if (runCatching { api.billStatus().enabled }.getOrDefault(false)) {
            api.billers().filter { it.category == "electricity" }
        } else {
            emptyList()
        }
        FormSetup(groupId?.let { api.group(it) }, billers)
    }
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { setup -> GroupForm(api, setup, onSaved) }
    }
}

@Composable
private fun GroupForm(api: SplitPayApi, setup: FormSetup, onSaved: (Int) -> Unit) {
    val editing = setup.group
    var name by remember { mutableStateOf(editing?.name.orEmpty()) }
    var note by remember { mutableStateOf(editing?.description.orEmpty()) }
    var purpose by remember { mutableStateOf(editing?.purpose ?: "rent") }
    var target by remember { mutableStateOf(editing?.targetAmount.orEmpty()) }
    var due by remember { mutableStateOf(editing?.dueDate ?: LocalDate.now().plusDays(14).toString()) }
    var repeats by remember { mutableStateOf(editing?.isRecurring ?: false) }
    var interval by remember { mutableStateOf(editing?.recurrenceInterval ?: "monthly") }
    var partial by remember { mutableStateOf(editing?.allowPartialPayout ?: false) }
    var payoutType by remember { mutableStateOf(editing?.payoutType ?: "bank_transfer") }
    var bank by remember { mutableStateOf(editing?.recipientBankCode.orEmpty()) }
    var accountNumber by remember { mutableStateOf("") }
    var accountName by remember { mutableStateOf(editing?.recipientAccountName.orEmpty()) }
    var biller by remember { mutableStateOf(editing?.billServiceId.orEmpty()) }
    var meterType by remember { mutableStateOf(editing?.billVariation?.ifBlank { null } ?: "prepaid") }
    var meter by remember { mutableStateOf(editing?.billCustomerId.orEmpty()) }
    var meterResult by remember { mutableStateOf<String?>(null) }
    var memberEntry by remember { mutableStateOf("") }
    var memberShare by remember { mutableStateOf("") }
    val members = remember { mutableStateListOf<MemberRow>() }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val isBill = payoutType == "bill_payment"

    fun meterBody(): JsonObject = buildJsonObject {
        put("service_id", biller)
        put("customer_id", meter.trim())
        put("variation", meterType)
    }

    fun body(): JsonObject = buildJsonObject {
        put("name", name.trim())
        put("description", note.trim())
        put("purpose", purpose)
        put("target_amount", target)
        put("due_date", due)
        put("is_recurring", repeats)
        put("recurrence_interval", if (repeats) interval else null)
        put("allow_partial_payout", partial)
        if (editing == null) put("payout_type", payoutType)
        if (isBill) {
            put("bill_service_id", biller)
            put("bill_customer_id", meter.trim())
            put("bill_variation", meterType)
        } else {
            put("recipient_bank_code", bank)
            put("recipient_bank_name", BANKS.first { it.first == bank }.second)
            put("recipient_account_name", accountName.trim())
            if (accountNumber.isNotEmpty()) put("recipient_account_number", accountNumber)
        }
        if (editing == null) {
            putJsonArray("members") {
                members.forEach { row ->
                    addJsonObject {
                        put("identifier", row.identifier)
                        if (row.share.isNotBlank()) put("contribution_share", row.share)
                    }
                }
            }
        }
    }

    val accountReady = accountNumber.length == 10 || (editing != null && accountNumber.isEmpty())
    val destinationReady = if (isBill) biller.isNotBlank() && meter.all(Char::isDigit) && meter.isNotBlank()
    else bank.isNotBlank() && accountReady && accountName.isNotBlank()

    Column(
        Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        OutlinedTextField(name, { name = it }, label = { Text("Group name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Picker("Purpose", PURPOSES, purpose) { purpose = it }
        AmountField("Target amount (₦)", target) { target = it }
        DateField("Due date", due) { due = it }
        OutlinedTextField(note, { note = it }, label = { Text("Note for members (optional)") }, modifier = Modifier.fillMaxWidth())
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(repeats, { repeats = it })
            Text("Repeat this group")
        }
        if (repeats) Picker("Repeats", INTERVALS, interval) { interval = it }

        Text("Who gets paid", style = MaterialTheme.typography.titleMedium)
        if (editing == null && setup.billers.isNotEmpty()) {
            Picker("Pay out by", PAYOUT_TYPES, payoutType) { payoutType = it }
        }
        if (isBill) {
            Picker("Electricity company", setup.billers.map { it.serviceId to it.name }, biller) { biller = it; meterResult = null }
            Picker("Meter type", METER_TYPES, meterType) { meterType = it; meterResult = null }
            OutlinedTextField(
                meter, { value -> meter = value.filter(Char::isDigit); meterResult = null },
                label = { Text("Meter number") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedButton(enabled = biller.isNotBlank() && meter.isNotBlank(), onClick = {
                scope.launch {
                    meterResult = try {
                        val info = api.checkMeter(meterBody())
                        if (info.valid) listOf(info.name, info.address).filter { it.isNotBlank() }.joinToString(", ").ifBlank { "Meter found." }
                        else "The biller couldn't find that meter (${info.message.ifBlank { "not found" }})."
                    } catch (e: kotlinx.coroutines.CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        e.userMessage()
                    }
                }
            }) { Text("Check this meter") }
            meterResult?.let { Text(it) }
        } else {
            Picker("Bank", BANKS, bank) { bank = it }
            OutlinedTextField(
                accountNumber, { value -> accountNumber = value.filter(Char::isDigit).take(10) },
                label = { Text(if (editing != null) "Account number (empty keeps the saved one)" else "Account number") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(accountName, { accountName = it }, label = { Text("Account name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(partial, { partial = it })
            Text("Allow me to pay out before the target is reached")
        }

        if (editing == null) {
            Text("Members", style = MaterialTheme.typography.titleMedium)
            Text("They need a SplitPay account. The target is shared equally, including you, unless you set a custom share.", style = MaterialTheme.typography.bodySmall)
            members.toList().forEach { row ->
                Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween, Alignment.CenterVertically) {
                    Text(if (row.share.isBlank()) row.identifier else "${row.identifier} · ${money(row.share)}", Modifier.weight(1f))
                    TextButton(onClick = { members.remove(row) }) { Text("Remove") }
                }
            }
            OutlinedTextField(memberEntry, { memberEntry = it }, label = { Text("Email or phone") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            AmountField("Custom share (₦, optional)", memberShare) { memberShare = it }
            OutlinedButton(enabled = memberEntry.isNotBlank(), onClick = {
                val entry = memberEntry.trim()
                if (members.none { it.identifier == entry }) members.add(MemberRow(entry, memberShare))
                memberEntry = ""
                memberShare = ""
            }) { Text("Add member") }
        }

        ErrorText(error)
        BusyButton(
            if (editing == null) "Create group" else "Save changes", busy,
            enabled = name.isNotBlank() && target.isNotBlank() && destinationReady,
        ) {
            scope.launch {
                busy = true
                error = null
                try {
                    if (editing == null && isBill) {
                        // As on the website: stop on a bad meter, but don't block when the biller is unreachable.
                        val info = runCatching { api.checkMeter(meterBody()) }.getOrNull()
                        if (info != null && !info.valid) {
                            error = "The biller couldn't find that meter (${info.message.ifBlank { "not found" }})."
                            return@launch
                        }
                    }
                    val saved = if (editing == null) api.createGroup(body()) else api.updateGroup(editing.id, body())
                    onSaved(saved.id)
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
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateField(label: String, value: String, onChange: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        OutlinedTextField(prettyDate(value), {}, readOnly = true, label = { Text(label) }, modifier = Modifier.fillMaxWidth())
        Box(Modifier.matchParentSize().clickable { open = true })
    }
    if (open) {
        val state = rememberDatePickerState(
            initialSelectedDateMillis = LocalDate.parse(value).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli(),
        )
        DatePickerDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { millis ->
                        onChange(Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate().toString())
                    }
                    open = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { open = false }) { Text("Close") } },
        ) { DatePicker(state) }
    }
}
