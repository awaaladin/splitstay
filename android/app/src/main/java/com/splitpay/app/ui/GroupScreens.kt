package com.splitpay.app.ui

import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.splitpay.app.data.BANKS
import com.splitpay.app.data.ContributeRequest
import com.splitpay.app.data.ContributeResponse
import com.splitpay.app.data.Group
import com.splitpay.app.data.GroupInput
import com.splitpay.app.data.Ledger
import com.splitpay.app.data.MemberInput
import com.splitpay.app.data.PURPOSES
import com.splitpay.app.data.SplitPayApi
import com.splitpay.app.data.userMessage
import kotlinx.coroutines.launch
import java.time.LocalDate

@Composable
fun GroupsScreen(api: SplitPayApi, padding: PaddingValues, onOpen: (Int) -> Unit) {
    val loader = rememberLoader { api.groups().results }
    ReloadOnResume(loader::reload)
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { groups ->
            if (groups.isEmpty()) {
                Box(Modifier.fillMaxSize().padding(24.dp), Alignment.Center) {
                    Text("No groups yet. Tap + to start one for your rent, light or any shared bill.")
                }
            } else {
                LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(groups, key = { it.id }) { GroupCard(it) { onOpen(it.id) } }
                }
            }
        }
    }
}

@Composable
private fun GroupCard(group: Group, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(group.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Text(
                    if (group.myMembership?.status == "invited") "Invited" else statusLabel(group.status),
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            LinearProgressIndicator(
                progress = { (group.progress.percent.toFloatOrNull() ?: 0f) / 100f },
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                "${money(group.progress.funded)} of ${money(group.progress.target)} · due ${prettyDate(group.dueDate)}",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

/** Refreshes when the member comes back from Paystack's checkout, or from anywhere else. */
@Composable
private fun ReloadOnResume(reload: () -> Unit) {
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        var first = true
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                if (first) first = false else reload()
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
}

@Composable
fun GroupDetailScreen(api: SplitPayApi, groupId: Int, padding: PaddingValues, onLeft: () -> Unit) {
    val loader = rememberLoader(groupId) {
        val group = api.group(groupId)
        // Invited members can't read the ledger yet.
        val ledger = if (group.myMembership?.status == "joined" || group.myMembership == null) {
            runCatching { api.ledger(groupId) }.getOrNull()
        } else {
            null
        }
        group to ledger
    }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var quote by remember { mutableStateOf<ContributeResponse?>(null) }
    var pending by remember { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf<ConfirmAction?>(null) }
    var inviting by remember { mutableStateOf(false) }

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

    // The return page is a logged-in web page the Custom Tab has no session for, so the app asks
    // the API to verify. The webhook confirms the payment even if the member never comes back.
    ReloadOnResume {
        val reference = pending
        if (reference != null) {
            pending = null
            act {
                val result = api.verify(reference)
                notice = when (result.status) {
                    "paid" -> "Payment received. Thank you."
                    "failed" -> "That payment didn't go through. You haven't been charged."
                    else -> "Your payment hasn't been confirmed yet. If you paid, it will show here shortly."
                }
                loader.reload()
            }
        } else {
            loader.reload()
        }
    }

    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { (group, ledger) ->
            val mine = group.myMembership
            val isOpen = group.status == "open" || group.status == "overdue"
            val me = mine?.user?.id
            val isAdmin = me != null && me == group.admin.id
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
                LabelValue("Organiser", group.admin.name)
                if (group.payoutType == "bank_transfer") {
                    LabelValue("Paid to", group.recipientAccountName.ifBlank { group.recipientBankName })
                    LabelValue("Account", "${group.recipientBankName} ${group.recipientAccount}".trim())
                } else if (group.billerName.isNotBlank()) {
                    LabelValue("Paid to", group.billerName)
                }

                notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
                ErrorText(error)

                if (mine != null) {
                    HorizontalDivider()
                    LabelValue("Your share", money(mine.share))
                    LabelValue("You've paid", money(mine.amountPaid))
                    LabelValue("You still owe", money(mine.outstanding))
                    if (mine.status == "invited" && isOpen) {
                        BusyButton("Accept invitation", busy) { act { api.accept(groupId); loader.reload() } }
                        OutlinedButton(onClick = { confirm = ConfirmAction.Leave }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                            Text("Decline")
                        }
                    } else if (mine.status == "joined" && isOpen && (mine.outstanding.toBigDecimalOrNull()?.signum() ?: 0) > 0) {
                        BusyButton("Pay ${money(mine.outstanding)}", busy) {
                            act { quote = api.contribute(groupId, ContributeRequest()) }
                        }
                    }
                }

                if (isAdmin && isOpen) {
                    OutlinedButton(onClick = { inviting = true }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                        Text("Add a member")
                    }
                }
                if (isAdmin && (group.status == "funded" || group.allowPartialPayout && isOpen)) {
                    OutlinedButton(onClick = { confirm = ConfirmAction.Payout }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                        Text("Pay out now")
                    }
                }
                if (isAdmin && isOpen) {
                    TextButton(onClick = { confirm = ConfirmAction.Cancel }, enabled = !busy) { Text("Cancel group") }
                }

                ledger?.let { History(it) }
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
                                    ConfirmAction.Leave -> { api.leave(groupId).orThrow(); onLeft() }
                                    ConfirmAction.Cancel -> { api.cancel(groupId); loader.reload() }
                                    ConfirmAction.Payout -> {
                                        api.payout(groupId).orThrow()
                                        notice = "Payout started."
                                        loader.reload()
                                    }
                                }
                            }
                        }) { Text("Yes") }
                    },
                    dismissButton = { TextButton(onClick = { confirm = null }) { Text("No") } },
                )
            }

            if (inviting) {
                var who by remember { mutableStateOf("") }
                AlertDialog(
                    onDismissRequest = { inviting = false },
                    title = { Text("Add a member") },
                    text = {
                        OutlinedTextField(who, { who = it }, label = { Text("Their email or phone number") }, singleLine = true)
                    },
                    confirmButton = {
                        TextButton(enabled = who.isNotBlank(), onClick = {
                            val identifier = who.trim()
                            inviting = false
                            act { api.addMember(groupId, MemberInput(identifier)); loader.reload() }
                        }) { Text("Add") }
                    },
                    dismissButton = { TextButton(onClick = { inviting = false }) { Text("Close") } },
                )
            }
        }
    }
}

private enum class ConfirmAction(val title: String, val body: String) {
    Leave("Decline this invitation?", "You won't be part of this group."),
    Cancel("Cancel this group?", "This can't be undone."),
    Payout("Pay out now?", "The money raised so far goes to the group's recipient. This can't be undone."),
}

private fun retrofit2.Response<Unit>.orThrow() {
    if (!isSuccessful) throw retrofit2.HttpException(this)
}

@Composable
private fun History(ledger: Ledger) {
    if (ledger.members.isNotEmpty()) {
        HorizontalDivider()
        Text("Members", style = MaterialTheme.typography.titleMedium)
        ledger.members.forEach { LabelValue(it.name, "${money(it.paid)} of ${money(it.share)}") }
    }
    if (ledger.results.isNotEmpty()) {
        HorizontalDivider()
        Text("Activity", style = MaterialTheme.typography.titleMedium)
        ledger.results.forEach { entry ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text(entry.title)
                    Text(
                        listOf(entry.actor, prettyDateTime(entry.at)).filter { it.isNotBlank() }.joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                entry.amount?.let { Text(money(it)) }
            }
        }
    }
}

@Composable
fun NewGroupScreen(api: SplitPayApi, padding: PaddingValues, onCreated: (Int) -> Unit) {
    var name by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var purpose by remember { mutableStateOf("rent") }
    var target by remember { mutableStateOf("") }
    var due by remember { mutableStateOf(LocalDate.now().plusDays(14).toString()) }
    var partial by remember { mutableStateOf(false) }
    var bank by remember { mutableStateOf("") }
    var accountNumber by remember { mutableStateOf("") }
    var accountName by remember { mutableStateOf("") }
    var memberEntry by remember { mutableStateOf("") }
    val members = remember { mutableStateListOf<String>() }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        OutlinedTextField(name, { name = it }, label = { Text("Group name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Picker("What's it for?", PURPOSES, purpose) { purpose = it }
        OutlinedTextField(
            target, { value -> target = value.filter { it.isDigit() || it == '.' } },
            label = { Text("Target amount (₦)") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            due, { due = it }, label = { Text("Due date (YYYY-MM-DD)") }, singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(note, { note = it }, label = { Text("Note for members (optional)") }, modifier = Modifier.fillMaxWidth())

        Text("Who gets paid", style = MaterialTheme.typography.titleMedium)
        Picker("Bank", BANKS, bank) { bank = it }
        OutlinedTextField(
            accountNumber, { value -> accountNumber = value.filter(Char::isDigit).take(10) },
            label = { Text("Account number") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(accountName, { accountName = it }, label = { Text("Account name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(partial, { partial = it })
            Text("Allow me to pay out before the target is reached")
        }

        Text("Members", style = MaterialTheme.typography.titleMedium)
        Text("They need a SplitPay account. The target is shared equally, including you.", style = MaterialTheme.typography.bodySmall)
        members.toList().forEach { member ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(member, Modifier.weight(1f))
                TextButton(onClick = { members.remove(member) }) { Text("Remove") }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(memberEntry, { memberEntry = it }, label = { Text("Email or phone") }, singleLine = true, modifier = Modifier.weight(1f))
            TextButton(enabled = memberEntry.isNotBlank(), onClick = {
                val entry = memberEntry.trim()
                if (entry !in members) members.add(entry)
                memberEntry = ""
            }) { Text("Add") }
        }

        ErrorText(error)
        BusyButton(
            "Create group", busy,
            enabled = name.isNotBlank() && target.isNotBlank() && bank.isNotBlank() && accountNumber.length == 10 && accountName.isNotBlank(),
        ) {
            scope.launch {
                busy = true
                error = null
                try {
                    val group = api.createGroup(
                        GroupInput(
                            name = name.trim(), description = note.trim(), purpose = purpose, targetAmount = target,
                            dueDate = due.trim(), allowPartialPayout = partial, recipientBankCode = bank,
                            recipientBankName = BANKS.first { it.first == bank }.second,
                            recipientAccountName = accountName.trim(), recipientAccountNumber = accountNumber,
                            members = members.map { MemberInput(it) },
                        ),
                    )
                    onCreated(group.id)
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
