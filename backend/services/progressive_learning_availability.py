"""Read personal availability from the same fine path that authorizes study."""
from services.learning_availability_state import _state


def progressive_personal_learning_state(conn, *, child, learning_service=None,
                                       learning_repository=None, supply=None, grade_open=True):
    if not grade_open:
        return _state('not_open', 0, 0, 0, '这个年级的课程还没有开放。')
    if learning_service is not None:
        service = learning_service.progressive_service()
    else:
        from repositories.progressive_learning_repository import ProgressiveLearningRepository
        from services.progressive_learning_service import ProgressiveLearningService
        if learning_repository is None:
            raise ValueError('an authoritative learning repository is required')
        def visible(connection, *, child, course):
            if course.get('grade_code') != child.get('grade_code'):
                return False
            return learning_repository.get_student_visible_course(
                connection, family_id=child['family_id'], child_id=child['id'],
                grade_code=child['grade_code'],
                grade_selection_revision=int(child.get('grade_selection_revision') or 0),
                course_id=course['id'], course_version=course['version'],
            ) is not None
        service = ProgressiveLearningService(ProgressiveLearningRepository(learning_repository.database),
                                             course_validator=visible)
    paths = [service.get_path(conn, child=child, subject=subject)
             for subject in ('chinese', 'math', 'english')]
    rows = {row['lessonId']: row for path in paths
            for row in path['lessons'] if row['gradeCode'] == child['grade_code']}
    ready = {str(path['nextLesson']['courseId']) + ':' + str(path['nextLesson']['courseVersion'])
             for path in paths if path.get('nextLesson') and path['nextLesson'].get('course')
             and path['nextLesson']['gradeCode'] == child['grade_code']}
    review = {str(row['courseId']) + ':' + str(row['courseVersion'])
              for row in rows.values() if row['status'] == 'mastered' and row.get('course')}
    published = {str(row['courseId']) + ':' + str(row['courseVersion'])
                 for row in rows.values() if row.get('course')}
    if ready:
        status, message = 'ready', '本年级下一课已准备好，可以按顺序学习。'
    elif rows and all(row['status'] == 'mastered' for row in rows.values()):
        status, message = 'scope_completed', '当前年级已经学会，可以复习巩固。'
    elif any((row.get('observation') or {}).get('canConfirm') for row in rows.values()):
        status, message = 'preparing', '这节课的学习已完成，请家长确认独立完成情况。'
    elif (supply or {}).get('paused') is True:
        status, message = 'paused', '下一课准备已暂停，学习进度会保留。'
    else:
        status, message = 'preparing', '本年级下一课正在准备，准备好后会按学习顺序出现。'
    return _state(status, len(ready), len(review), len(published), message)
