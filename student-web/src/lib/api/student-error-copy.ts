/** Keep the reason and receipt state while removing service names from UI copy.
 * This is for error messages only, never original questions or uploaded titles. */
export function studentErrorCopy(message: string) {
  return message
    .replace(/腾讯(?:云)?(?:\s*(?:AI|初判|批改))?/giu, "作业检查")
    .replace(/\btencent(?:\s*cloud)?\b/giu, "作业检查")
    .replace(/\bqwen[a-z0-9._-]*\b|\bdeepseek[a-z0-9._-]*\b|阿里(?:云)?(?:百炼)?|百炼|通义(?:千问)?/giu, "老师")
    .replace(/open\s*maic(?:\s*课堂)?/giu, "课堂")
    .replace(/\bAI\s*老师|\bAI\b/giu, "老师")
    .replace(/初判/gu, "检查提示");
}
