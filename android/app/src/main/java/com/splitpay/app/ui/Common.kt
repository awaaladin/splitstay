package com.splitpay.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.splitpay.app.data.userMessage
import java.math.BigDecimal
import java.text.NumberFormat
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

private val Navy900 = Color(0xFF102A56)
private val Navy400 = Color(0xFF8FA5D2)
private val Navy50 = Color(0xFFEEF2F9)
private val Navy950 = Color(0xFF0A1630)

@Composable
fun SplitPayTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) {
        darkColorScheme(
            primary = Navy400, onPrimary = Navy950, primaryContainer = Color(0xFF172D57),
            onPrimaryContainer = Navy50, background = Navy950, surface = Navy950,
        )
    } else {
        lightColorScheme(
            primary = Navy900, onPrimary = Color.White, primaryContainer = Navy50,
            onPrimaryContainer = Navy900, background = Color.White, surface = Color.White,
        )
    }
    MaterialTheme(colorScheme = colors, content = content)
}

private val naira: NumberFormat = NumberFormat.getNumberInstance(Locale.US).apply {
    minimumFractionDigits = 2
    maximumFractionDigits = 2
}

fun money(value: String?): String = "₦" + naira.format(value?.toBigDecimalOrNull() ?: BigDecimal.ZERO)

fun prettyDate(iso: String): String = runCatching {
    LocalDate.parse(iso).format(DateTimeFormatter.ofPattern("d MMM yyyy", Locale.ENGLISH))
}.getOrDefault(iso)

fun prettyDateTime(iso: String): String = runCatching {
    OffsetDateTime.parse(iso).format(DateTimeFormatter.ofPattern("d MMM, h:mm a", Locale.ENGLISH))
}.getOrDefault(iso)

fun statusLabel(status: String): String = when (status) {
    "paid_out" -> "Paid out"
    else -> status.replaceFirstChar { it.uppercase() }
}

/** One-shot load with loading, error+retry and a `reload` that callers can trigger after an action. */
class Loader<T> {
    var data by mutableStateOf<T?>(null)
    var error by mutableStateOf<String?>(null)
    var version by mutableStateOf(0)
    fun reload() { version++ }
}

@Composable
fun <T> rememberLoader(key: Any? = null, fetch: suspend () -> T): Loader<T> {
    val loader = remember(key) { Loader<T>() }
    LaunchedEffect(key, loader.version) {
        loader.error = null
        try {
            loader.data = fetch()
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            loader.error = e.userMessage()
        }
    }
    return loader
}

@Composable
fun <T> Loaded(loader: Loader<T>, content: @Composable (T) -> Unit) {
    val data = loader.data
    when {
        data != null -> content(data)
        loader.error != null -> Box(Modifier.fillMaxSize().padding(24.dp), Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(loader.error.orEmpty())
                OutlinedButton(onClick = loader::reload) { Text("Try again") }
            }
        }
        else -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
    }
}

@Composable
fun BusyButton(text: String, busy: Boolean, modifier: Modifier = Modifier.fillMaxWidth(), enabled: Boolean = true, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = modifier) {
        if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Text(text)
    }
}

@Composable
fun ErrorText(message: String?) {
    if (message != null) Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
}

@Composable
fun LabelValue(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Picker(label: String, options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
        OutlinedTextField(
            value = options.firstOrNull { it.first == selected }?.second.orEmpty(),
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) },
            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (value, name) ->
                DropdownMenuItem(text = { Text(name) }, onClick = { onSelect(value); open = false })
            }
        }
    }
}
