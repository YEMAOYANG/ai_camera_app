"use client";

import { ArrowLeft } from "lucide-react";
import { useState } from "react";

import { DocumentLink } from "@/components/navigation/document-link";
import { MiraMark } from "@/components/student/mira-mark";
import { Button } from "@/components/ui/button";
import type { LearningStartResponse } from "@/lib/contracts/learning";
import type { OpenMaicFormalRuntimeLaunch } from "@/lib/contracts/openmaic-runtime";

export function FullOpenMaicClassroom({
  start,
  launch,
}: {
  start: LearningStartResponse;
  launch: OpenMaicFormalRuntimeLaunch;
}) {
  const [frameLoaded, setFrameLoaded] = useState(false);
  const missing = launch.features.schemaVersion === "mira.openmaic.runtime-features.v2"
    ? launch.features.missing
    : [];
  if (missing.length > 0) {
    return (
      <main id="main-content" className="classroom-preparing-state">
        <p>课程制作中</p>
        <h1>完整互动课堂制作未完成</h1>
        <span>还有课堂内容或互动能力没有通过检查，准备好后就会自动开放。</span>
        <div>
          <Button asChild>
            <DocumentLink href="/learning">看看其他课程</DocumentLink>
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main
      id="main-content"
      className="full-openmaic-shell"
      aria-label="完整互动课堂"
    >
      <nav className="full-openmaic-toolbar" aria-label="课堂导航">
        <DocumentLink
          href="/learning"
          className="focus-ring full-openmaic-back"
          aria-label="返回课程列表"
        >
          <ArrowLeft className="size-5" aria-hidden="true" />
          <span>返回课程列表</span>
        </DocumentLink>
        <div className="full-openmaic-brand">
          <div className="full-openmaic-mark">
            <MiraMark compact />
          </div>
          <span className="full-openmaic-brand-divider" aria-hidden="true" />
          <span className="full-openmaic-context">
            <span>暖瞳课堂</span>
            <strong title={start.lesson.title}>{start.lesson.title}</strong>
          </span>
        </div>
      </nav>
      <section className="full-openmaic-stage" aria-label={`${start.lesson.title}课堂内容`}>
        {!frameLoaded ? (
          <div className="full-openmaic-stage__loading" aria-live="polite">
            <span />
            正在请老师进入课堂…
          </div>
        ) : null}
        {/* The origin is pinned by the BFF and by the route Permissions-Policy.
            The classroom needs its own storage, nested sandboxes and media runtime, so
            adding an iframe sandbox here would break the reviewed classroom. */}
        <iframe
          src={launch.launchUrl}
          title={`${start.lesson.title}完整互动课堂`}
          className="full-openmaic-frame"
          allow="microphone; autoplay; fullscreen"
          allowFullScreen
          // This only confirms the iframe document loaded. The embedded runtime
          // remains responsible for its own classroom-ready and error states.
          onLoad={() => setFrameLoaded(true)}
          referrerPolicy="no-referrer"
        />
      </section>
    </main>
  );
}
