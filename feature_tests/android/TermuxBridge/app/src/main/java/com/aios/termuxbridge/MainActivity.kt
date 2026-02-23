package com.aios.termuxbridge

import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.cardview.widget.CardView
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var outputText: TextView
    private lateinit var commandInput: EditText
    private lateinit var permissionCard: CardView
    private lateinit var permissionStatus: TextView
    private lateinit var permissionSteps: TextView
    private lateinit var openSettingsButton: Button
    private lateinit var controlsLayout: LinearLayout
    private lateinit var scrollView: ScrollView

    private val handler = Handler(Looper.getMainLooper())

    companion object {
        const val TERMUX_PERMISSION = "com.termux.permission.RUN_COMMAND"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
            setBackgroundColor(Color.parseColor("#FAFAFA"))
        }

        // Title
        val title = TextView(this).apply {
            text = "Termux Bridge"
            textSize = 28f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#1a1a1a"))
        }
        layout.addView(title)

        val subtitle = TextView(this).apply {
            text = "Run commands in Termux from this app"
            textSize = 14f
            setTextColor(Color.GRAY)
        }
        layout.addView(subtitle)

        // Permission Status Card
        permissionCard = CardView(this).apply {
            radius = 24f
            cardElevation = 8f
            setContentPadding(32, 32, 32, 32)
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.setMargins(0, 32, 0, 24)
            layoutParams = params
        }

        val cardContent = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        permissionStatus = TextView(this).apply {
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
        }
        cardContent.addView(permissionStatus)

        permissionSteps = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.parseColor("#444444"))
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.topMargin = 16
            layoutParams = params
        }
        cardContent.addView(permissionSteps)

        openSettingsButton = Button(this).apply {
            text = "Open App Settings"
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.topMargin = 24
            layoutParams = params
            setOnClickListener {
                val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.fromParts("package", packageName, null)
                }
                startActivity(intent)
            }
        }
        cardContent.addView(openSettingsButton)

        permissionCard.addView(cardContent)
        layout.addView(permissionCard)

        // Controls
        controlsLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        commandInput = EditText(this).apply {
            hint = "Enter command (e.g., ls -la)"
            setSingleLine(true)
            setBackgroundColor(Color.WHITE)
            setPadding(24, 24, 24, 24)
        }
        controlsLayout.addView(commandInput)

        val buttonRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.topMargin = 16
            layoutParams = params
        }

        val runButton = Button(this).apply {
            text = "Run"
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            params.marginEnd = 8
            layoutParams = params
            setOnClickListener {
                val cmd = commandInput.text.toString()
                if (cmd.isNotEmpty()) {
                    appendOutput("\n> $cmd\n")
                    runCmd("bash", arrayOf("-c", cmd))
                }
            }
        }
        buttonRow.addView(runButton)

        val testButton = Button(this).apply {
            text = "Test aio.py"
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            params.marginStart = 8
            layoutParams = params
            setOnClickListener {
                appendOutput("\n> python aio.py help\n")
                runCmd("python", arrayOf("/data/data/com.termux/files/home/aio/aio.py", "help"))
            }
        }
        buttonRow.addView(testButton)

        controlsLayout.addView(buttonRow)

        val outputLabel = TextView(this).apply {
            text = "Output:"
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.topMargin = 24
            layoutParams = params
        }
        controlsLayout.addView(outputLabel)

        outputText = TextView(this).apply {
            text = "Ready.\n"
            textSize = 13f
            setTextIsSelectable(true)
            setBackgroundColor(Color.parseColor("#1a1a1a"))
            setTextColor(Color.parseColor("#00FF00"))
            setPadding(24, 24, 24, 24)
            typeface = Typeface.MONOSPACE
        }

        scrollView = ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#1a1a1a"))
        }
        scrollView.addView(outputText)

        val scrollParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f
        )
        scrollParams.topMargin = 8
        controlsLayout.addView(scrollView, scrollParams)

        layout.addView(controlsLayout)
        setContentView(layout)

        // Set up result callback
        MyResultService.onResult = { stdout, stderr, exitCode ->
            handler.post {
                val result = if (exitCode == 0 && stdout.isNotEmpty()) {
                    stdout
                } else if (stderr.isNotEmpty()) {
                    "[ERR $exitCode] $stderr"
                } else if (stdout.isNotEmpty()) {
                    "[Exit $exitCode] $stdout"
                } else {
                    "[Exit $exitCode] (no output)"
                }
                appendOutput("$result\n")
            }
        }
    }

    override fun onResume() {
        super.onResume()
        updatePermissionStatus()
    }

    override fun onDestroy() {
        super.onDestroy()
        MyResultService.onResult = null
    }

    private fun appendOutput(text: String) {
        outputText.append(text)
        scrollView.post { scrollView.fullScroll(View.FOCUS_DOWN) }
    }

    private fun updatePermissionStatus() {
        val granted = ContextCompat.checkSelfPermission(this, TERMUX_PERMISSION) ==
            PackageManager.PERMISSION_GRANTED

        if (granted) {
            permissionCard.setCardBackgroundColor(Color.parseColor("#E8F5E9"))
            permissionStatus.text = "✓ Permission Granted"
            permissionStatus.setTextColor(Color.parseColor("#2E7D32"))
            permissionSteps.text = "If commands fail, run in Termux:\nmkdir -p ~/.termux && echo 'allow-external-apps=true' >> ~/.termux/termux.properties"
            openSettingsButton.visibility = View.GONE
            controlsLayout.visibility = View.VISIBLE
        } else {
            permissionCard.setCardBackgroundColor(Color.parseColor("#FFEBEE"))
            permissionStatus.text = "✗ Permission Required"
            permissionStatus.setTextColor(Color.parseColor("#C62828"))
            permissionSteps.text = "1. Tap 'Open App Settings' below\n2. Permissions > Additional permissions\n3. Enable 'Run commands in Termux'\n4. Return here"
            openSettingsButton.visibility = View.VISIBLE
            controlsLayout.visibility = View.GONE
        }
    }

    private fun runCmd(bin: String, args: Array<String>) {
        try {
            val intent = Intent().apply {
                setClassName("com.termux", "com.termux.app.RunCommandService")
                action = "com.termux.RUN_COMMAND"
                putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/$bin")
                putExtra("com.termux.RUN_COMMAND_ARGUMENTS", args)
                putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home")
                putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)
                putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", PendingIntent.getService(
                    this@MainActivity, System.currentTimeMillis().toInt(),
                    Intent(this@MainActivity, MyResultService::class.java),
                    PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_MUTABLE
                ))
            }
            startService(intent)
        } catch (e: SecurityException) {
            appendOutput("[Error] allow-external-apps not enabled.\nRun in Termux: mkdir -p ~/.termux && echo 'allow-external-apps=true' >> ~/.termux/termux.properties\n")
        } catch (e: Exception) {
            appendOutput("[Error] ${e.message}\n")
        }
    }
}
