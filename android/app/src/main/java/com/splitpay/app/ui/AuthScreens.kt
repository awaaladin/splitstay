package com.splitpay.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.splitpay.app.R
import com.splitpay.app.data.LoginRequest
import com.splitpay.app.data.RegisterRequest
import com.splitpay.app.data.Session
import com.splitpay.app.data.SplitPayApi
import com.splitpay.app.data.userMessage
import kotlinx.coroutines.launch

@Composable
fun AuthScreen(api: SplitPayApi, session: Session) {
    var registering by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var identifier by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Image(painterResource(R.drawable.ic_launcher), contentDescription = null, Modifier.padding(top = 32.dp).size(72.dp))
        Text("SplitPay", style = MaterialTheme.typography.headlineMedium)
        Text(
            if (registering) "Create your account" else "Sign in to your groups",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (registering) {
            OutlinedTextField(name, { name = it }, label = { Text("Full name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        }
        OutlinedTextField(
            identifier, { identifier = it },
            label = { Text(if (registering) "Email" else "Email or phone number") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth(),
        )
        if (registering) {
            OutlinedTextField(
                phone, { phone = it }, label = { Text("Phone number (optional)") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        OutlinedTextField(
            password, { password = it }, label = { Text("Password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        ErrorText(error)
        BusyButton(
            if (registering) "Create account" else "Sign in", busy,
            enabled = identifier.isNotBlank() && password.isNotBlank() && (!registering || name.isNotBlank()),
        ) {
            scope.launch {
                busy = true
                error = null
                try {
                    val tokens = if (registering) {
                        api.register(RegisterRequest(identifier.trim(), password, name.trim(), phone.trim()))
                    } else {
                        api.login(LoginRequest(identifier.trim(), password))
                    }
                    session.save(tokens)
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (e: Exception) {
                    error = e.userMessage()
                } finally {
                    busy = false
                }
            }
        }
        TextButton(onClick = { registering = !registering; error = null }) {
            Text(if (registering) "I already have an account" else "New here? Create an account")
        }
    }
}
