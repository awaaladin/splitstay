package com.splitpay.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.splitpay.app.data.Session
import com.splitpay.app.data.SplitPayApi
import com.splitpay.app.data.buildApi
import com.splitpay.app.ui.AccountScreen
import com.splitpay.app.ui.AuthScreen
import com.splitpay.app.ui.GroupDetailScreen
import com.splitpay.app.ui.GroupsScreen
import com.splitpay.app.ui.NewGroupScreen
import com.splitpay.app.ui.NotificationsScreen
import com.splitpay.app.ui.SplitPayTheme
import com.splitpay.app.ui.rememberUnreadCount

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val session = Session(applicationContext)
        val api = buildApi(session)
        setContent {
            SplitPayTheme {
                val signedIn by session.signedIn.collectAsState()
                if (signedIn) App(api, session) else AuthScreen(api, session)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun App(api: SplitPayApi, session: Session) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route ?: "groups"
    val onHome = route == "groups"
    val unread = rememberUnreadCount(api, entry)

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(titleFor(route)) },
                navigationIcon = {
                    if (!onHome) {
                        IconButton(onClick = { nav.popBackStack() }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                actions = {
                    if (onHome) {
                        IconButton(onClick = { nav.navigate("notifications") }) {
                            BadgedBox(badge = { if (unread > 0) Badge { Text("$unread") } }) {
                                Icon(Icons.Filled.Notifications, contentDescription = "Notifications")
                            }
                        }
                        IconButton(onClick = { nav.navigate("account") }) {
                            Icon(Icons.Filled.Person, contentDescription = "Account")
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            if (onHome) {
                FloatingActionButton(onClick = { nav.navigate("new") }) {
                    Icon(Icons.Filled.Add, contentDescription = "New group")
                }
            }
        },
    ) { padding -> Routes(nav, api, session, padding) }
}

private fun titleFor(route: String): String = when (route) {
    "new" -> "New group"
    "notifications" -> "Notifications"
    "account" -> "Account"
    "groups/{id}" -> "Group"
    else -> "My groups"
}

@Composable
private fun Routes(nav: NavHostController, api: SplitPayApi, session: Session, padding: PaddingValues) {
    val idArgument = remember { listOf(navArgument("id") { type = NavType.IntType }) }
    NavHost(nav, startDestination = "groups") {
        composable("groups") { GroupsScreen(api, padding) { nav.navigate("groups/$it") } }
        composable("groups/{id}", idArgument) { entry ->
            GroupDetailScreen(api, entry.arguments!!.getInt("id"), padding, onLeft = { nav.popBackStack() })
        }
        composable("new") {
            NewGroupScreen(api, padding) { id ->
                nav.navigate("groups/$id") { popUpTo("new") { inclusive = true } }
            }
        }
        composable("notifications") { NotificationsScreen(api, padding) { nav.navigate("groups/$it") } }
        composable("account") { AccountScreen(api, session, padding) }
    }
}
