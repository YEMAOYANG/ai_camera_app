import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';

/// The same editable identity form is used during setup and in child settings.
class ChildLearningIdentityFields extends StatefulWidget {
  const ChildLearningIdentityFields({
    super.key,
    this.editing = false,
    required this.nickname,
    required this.schoolYearStartYear,
    required this.activeStageCode,
    required this.selected,
    required this.enabled,
    required this.onNicknameChanged,
    required this.onStageChanged,
    required this.onGradeSelected,
  });

  final bool editing;
  final String nickname;
  final int schoolYearStartYear;
  final String activeStageCode;
  final ChildGradeOption? selected;
  final bool enabled;
  final ValueChanged<String> onNicknameChanged;
  final ValueChanged<String> onStageChanged;
  final ValueChanged<ChildGradeOption> onGradeSelected;

  @override
  State<ChildLearningIdentityFields> createState() =>
      _ChildLearningIdentityFieldsState();
}

class _ChildLearningIdentityFieldsState
    extends State<ChildLearningIdentityFields> {
  late final TextEditingController _name;
  final _nameFocus = FocusNode();
  bool _gradesExpanded = true;
  bool _stageExpanded = true;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.nickname);
    _gradesExpanded = widget.selected == null;
    _stageExpanded = !widget.editing;
  }

  @override
  void didUpdateWidget(covariant ChildLearningIdentityFields oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.nickname != oldWidget.nickname &&
        widget.nickname != _name.text) {
      _name.value = TextEditingValue(
        text: widget.nickname,
        selection: TextSelection.collapsed(offset: widget.nickname.length),
      );
    }
    if (widget.activeStageCode != oldWidget.activeStageCode) {
      _gradesExpanded = true;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _nameFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selected = widget.selected?.stageCode == widget.activeStageCode
        ? widget.selected
        : null;
    final options = widget.activeStageCode == 'primary'
        ? ChildGradeOption.primary
        : ChildGradeOption.kindergarten;
    final textScale = MediaQuery.textScalerOf(context).scale(16) / 16;
    return Material(
      color: AppColors.surfaceElevated,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.card),
        side: const BorderSide(color: AppColors.borderSoft),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final stacked = constraints.maxWidth < 290 || textScale > 1.2;
                final field = TextField(
                  key: const ValueKey('setupInput_孩子称呼'),
                  controller: _name,
                  focusNode: _nameFocus,
                  enabled: widget.enabled,
                  textAlign: stacked ? TextAlign.start : TextAlign.end,
                  textInputAction: TextInputAction.done,
                  inputFormatters: [LengthLimitingTextInputFormatter(12)],
                  onChanged: widget.onNicknameChanged,
                  onSubmitted: (_) => _nameFocus.unfocus(),
                  style: const TextStyle(
                    fontSize: 15,
                    color: AppColors.ink,
                    height: 1.4,
                  ),
                  decoration: const InputDecoration(
                    filled: false,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                    hintText: '例如：乐乐',
                    hintStyle: TextStyle(fontSize: 15, color: AppColors.muted),
                    contentPadding: EdgeInsets.symmetric(vertical: 13),
                  ),
                );
                return Semantics(
                  label: '孩子称呼',
                  child: Container(
                    key: const ValueKey('setupField_孩子称呼'),
                    child: stacked
                        ? Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const SizedBox(height: 12),
                              const _FieldLabel('孩子称呼'),
                              field,
                            ],
                          )
                        : Row(
                            children: [
                              const _FieldLabel('孩子称呼'),
                              const SizedBox(width: 24),
                              Expanded(child: field),
                              const SizedBox(width: 6),
                              const Icon(
                                Icons.edit_outlined,
                                size: 17,
                                color: AppColors.muted,
                              ),
                            ],
                          ),
                  ),
                );
              },
            ),
          ),
          const Divider(height: 1, color: AppColors.borderSoft),
          if (!_stageExpanded)
            InkWell(
              onTap: widget.enabled
                  ? () => setState(() => _stageExpanded = true)
                  : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 14,
                ),
                child: Row(
                  children: [
                    const _FieldLabel('学段'),
                    const Spacer(),
                    Text(
                      widget.activeStageCode == 'primary' ? '小学' : '幼儿园',
                      style: const TextStyle(fontSize: 15),
                    ),
                    const SizedBox(width: 10),
                    const Icon(
                      Icons.keyboard_arrow_down,
                      size: 21,
                      color: AppColors.muted,
                    ),
                  ],
                ),
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final stages = _StageControl(
                    selected: widget.activeStageCode,
                    enabled: widget.enabled,
                    onChanged: (stage) {
                      _nameFocus.unfocus();
                      widget.onStageChanged(stage);
                      if (widget.editing) {
                        setState(() => _stageExpanded = false);
                      }
                    },
                  );
                  if (constraints.maxWidth < 290 || textScale > 1.2) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const _FieldLabel('学段'),
                        const SizedBox(height: 12),
                        stages,
                      ],
                    );
                  }
                  return Row(
                    children: [
                      const Expanded(child: _FieldLabel('学段')),
                      SizedBox(width: 178, child: stages),
                    ],
                  );
                },
              ),
            ),
          const Divider(height: 1, color: AppColors.borderSoft),
          Semantics(
            expanded: _gradesExpanded,
            child: InkWell(
              key: const ValueKey('childGradeDisclosure'),
              onTap: widget.enabled
                  ? () {
                      _nameFocus.unfocus();
                      setState(() => _gradesExpanded = !_gradesExpanded);
                    }
                  : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 14,
                ),
                child: Row(
                  children: [
                    const _FieldLabel('年级'),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Text(
                        selected?.gradeLabel ?? '请选择',
                        textAlign: TextAlign.end,
                        style: TextStyle(
                          fontSize: 15,
                          color: selected == null
                              ? AppColors.muted
                              : AppColors.ink,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Icon(
                      _gradesExpanded
                          ? Icons.keyboard_arrow_up
                          : Icons.keyboard_arrow_down,
                      size: 21,
                      color: AppColors.muted,
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (_gradesExpanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 2, 16, 18),
              child: Semantics(
                label: widget.activeStageCode == 'primary'
                    ? '选择小学年级'
                    : '选择幼儿园年级',
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final columns =
                        constraints.maxWidth < 280 || textScale > 1.2 ? 2 : 3;
                    final width =
                        (constraints.maxWidth - 10 * (columns - 1)) / columns;
                    return Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        for (final option in options)
                          SizedBox(
                            width: width,
                            child: _GradeChoice(
                              option: option,
                              selected: selected?.code == option.code,
                              enabled: widget.enabled,
                              onTap: () {
                                _nameFocus.unfocus();
                                widget.onGradeSelected(option);
                                setState(() => _gradesExpanded = false);
                              },
                            ),
                          ),
                      ],
                    );
                  },
                ),
              ),
            ),
          if (!widget.editing)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Text(
                '${widget.schoolYearStartYear}—${widget.schoolYearStartYear + 1} 学年',
                style: const TextStyle(
                  fontSize: 13,
                  height: 1.4,
                  color: AppColors.muted,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(
      fontSize: 15,
      fontWeight: FontWeight.w500,
      color: AppColors.ink,
      height: 1.4,
    ),
  );
}

class _StageControl extends StatelessWidget {
  const _StageControl({
    required this.selected,
    required this.enabled,
    required this.onChanged,
  });
  final String selected;
  final bool enabled;
  final ValueChanged<String> onChanged;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(3),
    decoration: BoxDecoration(
      color: AppColors.surfaceStrong,
      borderRadius: BorderRadius.circular(AppRadii.card),
    ),
    child: Row(
      children: [
        for (final stage in const [('kindergarten', '幼儿园'), ('primary', '小学')])
          Expanded(
            child: Semantics(
              selected: selected == stage.$1,
              button: true,
              enabled: enabled,
              child: AnimatedContainer(
                key: ValueKey('gradeStage_${stage.$1}'),
                constraints: const BoxConstraints(
                  minHeight: AppControls.minTouchTarget,
                ),
                duration: AppMotion.duration(context, 160),
                decoration: BoxDecoration(
                  color: selected == stage.$1
                      ? AppColors.brandWash
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(AppRadii.card),
                ),
                child: InkWell(
                  onTap: enabled ? () => onChanged(stage.$1) : null,
                  borderRadius: BorderRadius.circular(AppRadii.card),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      vertical: 9,
                      horizontal: 8,
                    ),
                    child: Text(
                      stage.$2,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 15,
                        height: 1.4,
                        fontWeight: FontWeight.w500,
                        color: selected == stage.$1
                            ? AppColors.brandDeep
                            : AppColors.ink,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    ),
  );
}

class _GradeChoice extends StatelessWidget {
  const _GradeChoice({
    required this.option,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });
  final ChildGradeOption option;
  final bool selected, enabled;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    selected: selected,
    enabled: enabled,
    child: AnimatedContainer(
      duration: AppMotion.duration(context, 160),
      decoration: BoxDecoration(
        color: selected ? AppColors.brandWash : AppColors.surfaceElevated,
        borderRadius: BorderRadius.circular(AppRadii.card),
        border: Border.all(
          color: selected ? AppColors.brand : AppColors.border,
        ),
      ),
      child: InkWell(
        key: ValueKey('gradeOption_${option.code}'),
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(AppRadii.card),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 13, horizontal: 4),
          child: Text(
            option.gradeLabel,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 15,
              height: 1.4,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
              color: selected ? AppColors.brandDeep : AppColors.ink,
            ),
          ),
        ),
      ),
    ),
  );
}
