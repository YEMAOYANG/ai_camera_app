import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/care/application/parent_review_realtime.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';

Future<void> showParentReviewSheet(
  BuildContext context, {
  required String reviewId,
  required String summary,
}) async {
  await showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.52,
    child: _ParentReviewSheetBody(reviewId: reviewId, summary: summary),
  );
}

class _ParentReviewSheetBody extends ConsumerStatefulWidget {
  const _ParentReviewSheetBody({
    required this.reviewId,
    required this.summary,
  });

  final String reviewId;
  final String summary;

  @override
  ConsumerState<_ParentReviewSheetBody> createState() =>
      _ParentReviewSheetBodyState();
}

class _ParentReviewSheetBodyState extends ConsumerState<_ParentReviewSheetBody> {
  var _submitting = false;

  Future<void> _acknowledge() async {
    if (_submitting) return;
    setState(() => _submitting = true);
    try {
      await ref.read(careRepositoryProvider).acknowledgeParentReview(
        reviewId: widget.reviewId,
      );
      ref.read(pendingParentReviewsOverrideProvider.notifier).state =
          ref
              .read(pendingParentReviewsOverrideProvider)
              .where((item) => item.id != widget.reviewId)
              .toList();
      if (!mounted) return;
      Navigator.of(context).pop();
      showAppToast(context, '已记录你的确认');
    } catch (error) {
      if (!mounted) return;
      showAppToast(context, '暂时无法确认，请稍后再试');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: '需要你看一下',
      subtitle: widget.summary,
      scrollable: false,
      footer: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppPrimaryButton(
            label: '已了解',
            loading: _submitting,
            onTap: _submitting ? null : _acknowledge,
          ),
          const SizedBox(height: 8),
          AppSecondaryButton(
            label: '去看看实时画面',
            onTap: () {
              Navigator.of(context).pop();
              context.go(AppRoute.live.path);
            },
          ),
        ],
      ),
      child: Text(
        '摄像头提醒多次后，需要你确认一下当前情况。',
        style: TextStyle(
          color: AppColors.muted.withValues(alpha: 0.92),
          fontFamily: AppTypography.systemFont,
          fontSize: 13,
          fontWeight: FontWeight.w600,
          height: 1.45,
        ),
      ),
    );
  }
}
