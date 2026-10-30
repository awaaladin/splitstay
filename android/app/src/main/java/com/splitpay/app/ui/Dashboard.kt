package com.splitpay.app.ui

import android.content.Context
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.splitpay.app.BuildConfig
import com.splitpay.app.data.Group
import com.splitpay.app.data.Notification
import com.splitpay.app.data.SplitPayApi
import java.math.BigDecimal

/** The website's public pages, opened as they are so the app can't drift from them. */
val SITE_PAGES = listOf(
    "How to use SplitPay" to "/guide/",
    "Fees" to "/fees/",
    "About" to "/about/",
    "Contact us" to "/contact/",
    "Privacy" to "/privacy/",
    "Terms of use" to "/terms/",
)

fun openPage(context: Context, path: String) {
    CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(BuildConfig.SITE_URL + path))
}

fun String?.decimal(): BigDecimal = this?.toBigDecimalOrNull() ?: BigDecimal.ZERO

private val Group.isOpen get() = status == "open" || status == "overdue"
private val Group.isInvited get() = myMembership?.status == "invited" && myMembership.user.id != admin.id
private val Group.owes get() = isOpen && myMembership?.status == "joined" && myMembership.outstanding.decimal().signum() > 0

private data class Home(val groups: List<Group>, val recent: List<Notification>)

@Composable
fun DashboardScreen(api: SplitPayApi, padding: PaddingValues, onOpen: (Int) -> Unit, onNotifications: () -> Unit) {
    val loader = rememberLoader {
        val groups = api.groups().results.sortedBy { it.dueDate }
        val recent = runCatching { api.notifications().results.take(5) }.getOrDefault(emptyList())
        Home(groups, recent)
    }
    ReloadOnResume(loader::reload)
    Box(Modifier.fillMaxSize().padding(padding)) {
        Loaded(loader) { home ->
            val invitations = home.groups.filter { it.isInvited }
            val cards = home.groups.filterNot { it.isInvited }
            val owing = cards.filter { it.owes }
            val active = cards.filter { it.status in setOf("open", "overdue", "funded") }
            val closed = cards.filter { it.status == "paid_out" || it.status == "cancelled" }
            LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            LabelValue("Active groups", "${active.size}")
                            LabelValue("You owe", money(owing.fold(BigDecimal.ZERO) { sum, g -> sum + g.myMembership?.outstanding.decimal() }.toPlainString()))
                            LabelValue("You've contributed", money(cards.fold(BigDecimal.ZERO) { sum, g -> sum + g.myMembership?.amountPaid.decimal() }.toPlainString()))
                        }
                    }
                }
                if (home.groups.isEmpty()) {
                    item { Text("No groups yet. Tap + to start one for your rent, light or any shared bill.") }
                }
                section("Invitations", "invite", invitations, onOpen)
                section("To pay", "owe", owing, onOpen)
                section("Active", "active", active, onOpen)
                section("Closed", "closed", closed, onOpen)
                if (home.recent.isNotEmpty()) {
                    item {
                        Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween, Alignment.CenterVertically) {
                            Text("Recent activity", style = MaterialTheme.typography.titleMedium)
                            TextButton(onClick = onNotifications) { Text("See all") }
                        }
                    }
                    items(home.recent, key = { "note${it.id}" }) { note ->
                        Column {
                            Text(note.title)
                            Text(prettyDateTime(note.createdAt), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.section(
    title: String, prefix: String, groups: List<Group>, onOpen: (Int) -> Unit,
) {
    if (groups.isEmpty()) return
    item { Text(title, style = MaterialTheme.typography.titleMedium) }
    items(groups, key = { "$prefix${it.id}" }) { group -> GroupCard(group) { onOpen(group.id) } }
}

@Composable
private fun GroupCard(group: Group, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(group.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Text(if (group.isInvited) "Invited" else statusLabel(group.status), style = MaterialTheme.typography.labelMedium)
            }
            LinearProgressIndicator(
                progress = { (group.progress.percent.toFloatOrNull() ?: 0f) / 100f },
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                "${money(group.progress.funded)} of ${money(group.progress.target)} · due ${prettyDate(group.dueDate)}",
                style = MaterialTheme.typography.bodySmall,
            )
            if (group.owes) Text("You owe ${money(group.myMembership?.outstanding)}", style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Refreshes when the member comes back from Paystack's checkout, or from anywhere else. */
@Composable
fun ReloadOnResume(reload: () -> Unit) {
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
