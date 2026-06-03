package com.miraguardian.mira_guardian_app

import android.app.DatePickerDialog
import android.content.Context
import android.content.DialogInterface
import android.content.res.Configuration
import android.view.ContextThemeWrapper
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.Calendar
import java.util.Locale

class MainActivity : FlutterActivity() {
    private val nativeDatePickerChannelName = "ai_camera_app/native_date_picker"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            nativeDatePickerChannelName
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "pickDate" -> showNativeDatePicker(call.arguments, result)
                else -> result.notImplemented()
            }
        }
    }

    private fun showNativeDatePicker(arguments: Any?, result: MethodChannel.Result) {
        val args = arguments as? Map<*, *>
        val title = args?.get("title") as? String ?: "选择日期"
        val locale = parseLocale(args?.get("locale") as? String)
        val initialDate = parseDate(args?.get("initialDate") as? String)
        val minDate = parseDate(args?.get("minDate") as? String)
        val maxDate = parseDate(args?.get("maxDate") as? String)

        if (initialDate == null || minDate == null || maxDate == null) {
            result.error("invalid_arguments", "日期参数不正确", null)
            return
        }

        var completed = false
        fun finish(value: String?) {
            if (completed) return
            completed = true
            result.success(value)
        }

        val dialog = DatePickerDialog(
            ContextThemeWrapper(
                localizedContext(locale),
                android.R.style.Theme_Material_Light_Dialog_Alert
            ),
            { _, year, month, dayOfMonth ->
                finish(formatDate(year, month, dayOfMonth))
            },
            initialDate.get(Calendar.YEAR),
            initialDate.get(Calendar.MONTH),
            initialDate.get(Calendar.DAY_OF_MONTH)
        )

        dialog.setTitle(title)
        dialog.datePicker.minDate = minDate.timeInMillis
        dialog.datePicker.maxDate = maxDate.timeInMillis
        dialog.setButton(DialogInterface.BUTTON_POSITIVE, "确定", dialog)
        dialog.setButton(DialogInterface.BUTTON_NEGATIVE, "取消") { _, _ -> finish(null) }
        dialog.setOnCancelListener { finish(null) }
        dialog.show()
    }

    private fun localizedContext(locale: Locale): Context {
        val configuration = Configuration(resources.configuration)
        configuration.setLocale(locale)
        return createConfigurationContext(configuration)
    }

    private fun parseLocale(value: String?): Locale {
        return when (value) {
            "zh_CN", "zh-Hans", "zh-Hans-CN" -> Locale.SIMPLIFIED_CHINESE
            else -> Locale.getDefault()
        }
    }

    private fun parseDate(value: String?): Calendar? {
        if (value.isNullOrBlank()) return null
        val parts = value.split("-")
        if (parts.size != 3) return null

        val year = parts[0].toIntOrNull() ?: return null
        val month = parts[1].toIntOrNull() ?: return null
        val day = parts[2].toIntOrNull() ?: return null

        val calendar = Calendar.getInstance(Locale.SIMPLIFIED_CHINESE)
        calendar.isLenient = false
        calendar.set(Calendar.YEAR, year)
        calendar.set(Calendar.MONTH, month - 1)
        calendar.set(Calendar.DAY_OF_MONTH, day)
        calendar.set(Calendar.HOUR_OF_DAY, 0)
        calendar.set(Calendar.MINUTE, 0)
        calendar.set(Calendar.SECOND, 0)
        calendar.set(Calendar.MILLISECOND, 0)

        return try {
            calendar.time
            calendar
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private fun formatDate(year: Int, month: Int, day: Int): String {
        return "%04d-%02d-%02d".format(Locale.US, year, month + 1, day)
    }
}
