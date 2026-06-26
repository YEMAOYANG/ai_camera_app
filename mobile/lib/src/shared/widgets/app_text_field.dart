import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

class AppTextField extends StatefulWidget {
  const AppTextField({
    required this.label,
    required this.icon,
    this.controller,
    this.value,
    this.onChanged,
    this.keyboardType,
    this.inputFormatters,
    this.errorText,
    this.hintText,
    this.obscureText = false,
    this.readOnly = false,
    this.onTap,
    this.suffixIcon,
    this.minLines = 1,
    super.key,
  }) : assert(
         controller != null || value != null,
         'Provide either controller or value.',
       );

  final String label;
  final IconData icon;
  final TextEditingController? controller;
  final String? value;
  final ValueChanged<String>? onChanged;
  final TextInputType? keyboardType;
  final List<TextInputFormatter>? inputFormatters;
  final String? errorText;
  final String? hintText;
  final bool obscureText;
  final bool readOnly;
  final VoidCallback? onTap;
  final IconData? suffixIcon;
  final int minLines;

  @override
  State<AppTextField> createState() => _AppTextFieldState();
}

class _AppTextFieldState extends State<AppTextField> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late final bool _ownsController;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    _controller =
        widget.controller ?? TextEditingController(text: widget.value ?? '');
    _focusNode = FocusNode();
  }

  @override
  void didUpdateWidget(covariant AppTextField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_ownsController &&
        widget.value != null &&
        widget.value != _controller.text &&
        widget.value != oldWidget.value) {
      _controller.value = TextEditingValue(
        text: widget.value!,
        selection: TextSelection.collapsed(offset: widget.value!.length),
      );
    }
  }

  @override
  void dispose() {
    if (_ownsController) _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasError = widget.errorText != null;

    return ListenableBuilder(
      listenable: Listenable.merge([_controller, _focusNode]),
      builder: (context, _) {
        final focused = _focusNode.hasFocus;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.label,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            AnimatedContainer(
              duration: AppMotion.duration(context, 160),
              decoration: BoxDecoration(
                color: _controller.text.trim().isEmpty
                    ? AppColors.surfaceSoft
                    : AppColors.surfaceElevated,
                borderRadius: BorderRadius.circular(AppRadii.input),
                border: Border.all(
                  color: hasError
                      ? AppColors.danger
                      : focused
                      ? AppColors.focus
                      : AppColors.borderSoft,
                  width: focused ? 1.1 : 1,
                ),
              ),
              child: Row(
                crossAxisAlignment: widget.minLines > 1
                    ? CrossAxisAlignment.start
                    : CrossAxisAlignment.center,
                children: [
                  Padding(
                    padding: EdgeInsets.only(
                      left: 13,
                      top: widget.minLines > 1 ? 15 : 0,
                    ),
                    child: Icon(
                      widget.icon,
                      color: hasError
                          ? AppColors.danger
                          : focused
                          ? AppColors.brandDeep
                          : AppColors.subtle,
                      size: 18,
                    ),
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      focusNode: _focusNode,
                      obscureText: widget.obscureText,
                      readOnly: widget.readOnly,
                      showCursor: widget.readOnly ? false : null,
                      keyboardType: widget.keyboardType,
                      inputFormatters: widget.inputFormatters,
                      minLines: widget.minLines,
                      maxLines: widget.obscureText
                          ? 1
                          : widget.minLines == 1
                          ? 1
                          : 6,
                      onTap: widget.onTap,
                      onChanged: widget.onChanged,
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        height: 1.2,
                      ),
                      decoration: InputDecoration(
                        filled: false,
                        fillColor: Colors.transparent,
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        errorBorder: InputBorder.none,
                        focusedErrorBorder: InputBorder.none,
                        disabledBorder: InputBorder.none,
                        hintText: widget.hintText,
                        hintStyle: const TextStyle(
                          color: AppColors.subtle,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          height: 1.2,
                        ),
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(
                          vertical: 14,
                        ),
                      ),
                    ),
                  ),
                  if (widget.suffixIcon != null) ...[
                    const SizedBox(width: 8),
                    Padding(
                      padding: EdgeInsets.only(
                        top: widget.minLines > 1 ? 15 : 0,
                      ),
                      child: Icon(
                        widget.suffixIcon,
                        color: focused ? AppColors.brandDeep : AppColors.subtle,
                        size: 18,
                      ),
                    ),
                  ],
                  const SizedBox(width: 12),
                ],
              ),
            ),
            AnimatedSwitcher(
              duration: AppMotion.duration(context, 160),
              child: widget.errorText == null
                  ? const SizedBox.shrink()
                  : Padding(
                      key: ValueKey(widget.errorText),
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        widget.errorText!,
                        style: const TextStyle(
                          color: AppColors.danger,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
            ),
          ],
        );
      },
    );
  }
}
