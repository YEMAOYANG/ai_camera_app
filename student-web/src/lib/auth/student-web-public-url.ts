import { allowsLocalLanProductionHttp } from "@/lib/security/local-lan-production";

export class StudentWebPublicUrlError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StudentWebPublicUrlError";
  }
}

export function studentWebPublicOrigin() {
  const configured = process.env.MIRA_STUDENT_WEB_PUBLIC_URL?.trim();
  if (!configured) {
    throw new StudentWebPublicUrlError("学生网页公开地址尚未配置");
  }

  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    throw new StudentWebPublicUrlError("学生网页公开地址格式无效");
  }

  const hasRootOnly = (url.pathname === "/" || url.pathname === "") && !url.search && !url.hash;
  const isHttp = url.protocol === "http:" || url.protocol === "https:";
  if (!isHttp || url.username || url.password || !hasRootOnly) {
    throw new StudentWebPublicUrlError("学生网页公开地址必须是没有路径、参数或账号信息的 http(s) 地址");
  }
  if (
    process.env.NODE_ENV === "production"
    && url.protocol !== "https:"
    && !allowsLocalLanProductionHttp(url)
  ) {
    throw new StudentWebPublicUrlError("正式环境的学生网页公开地址必须使用 HTTPS");
  }

  return url.origin;
}
