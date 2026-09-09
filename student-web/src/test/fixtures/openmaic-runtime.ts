export const sampleGenerationContractFixture = {
  schemaVersion: "mira.openmaic.sample-classroom.v2",
  sampleMode: "primary_1_math_number_sense_20_v1",
  authority: {
    courseContext: "mira_active_catalog_release",
    studentContext: "authenticated_learning_session",
    clientOverridesAllowed: false,
  },
  course: {
    id: "course-sample-math",
    version: "1",
    releaseId: "release-sample-math",
    packageId: "package-sample-math",
    packageVersion: 1,
    gradeCode: "primary_1",
    gradeLabel: "小学一年级",
    subjectCode: "math",
    subjectLabel: "数学",
    skill: {
      gradeCode: "primary_1",
      subject: "math",
      curriculumVersion: "mira.primary.2026-fall.v1",
      boundaryVersion: "mira.primary.2026-fall.v1:number_sense_20:0123456789abcdef",
      skillId: "number_sense_20",
      skillTitle: "20以内数感",
      learningObjectives: ["比较20以内数的大小", "理解数的组成与顺序"],
      allowedContent: ["数数", "数位雏形", "大小比较"],
      excludedContent: ["负数", "乘除法", "分数", "小数"],
      prerequisiteSkills: [],
      language: "zh-CN",
      estimatedMinutes: 10,
    },
    title: "20以内数感互动课堂",
    objective: "比较20以内数的大小并理解数的组成与顺序",
  },
  learnerConstraints: {
    developmentStage: "early_primary_grade_1",
    recommendedAgeBand: "6-8",
    language: "zh-CN",
    durationMinutes: 10,
    reading: "短句、口语化指令、一次只要求一个动作",
    visuals: "用可数物和数轴支持20以内数量、顺序和大小比较",
    prohibitedContent: ["负数", "乘除法", "分数", "小数"],
  },
  teacher: {
    profile: {
      id: "mira_math_clear",
      version: 2,
      displayName: "小数老师",
      languageCode: "zh-CN",
      teachingStyle: "clear_structured",
    },
    voiceIdentity: {
      schemaVersion: "mira.openmaic.qwen3-voice.v1",
      teacherProfile: { id: "mira_math_clear", version: 2 },
      voiceConfig: {
        providerId: "qwen-tts",
        modelId: "qwen3-tts-flash",
        voiceId: "Serena",
      },
      selectionId: "qwen-tts::Serena",
      displayName: "苏瑶 (Serena)",
      languageCode: "zh-CN",
    },
  },
  requiredClassroom: {
    features: [
      "slides",
      "quiz",
      "simulation",
      "html_game",
      "3d_visualization",
      "multi_agent_roundtable",
      "teacher_actions",
    ],
    exactSceneCount: 10,
    minimumSlideScenes: 2,
    sceneTypes: ["slide", "quiz", "interactive"],
    interactive: {
      requiredWidgetTypes: ["simulation", "game", "visualization3d"],
      widgetOutlineRequired: true,
      embeddedHtmlRequired: true,
      controlsRequired: true,
    },
    multiAgent: {
      teacherRequired: true,
      minimumPeerAgents: 3,
      minimumDiscussionActions: 2,
      distinctPeerDiscussionsRequired: true,
    },
    teacherActionsRequired: true,
    narration: {
      requiredForEveryScene: true,
      transcriptRequired: true,
    },
  },
  speechAudioContract: {
    schemaVersion: "mira.openmaic.speech-audio.v1",
    requiredForEverySpeechAction: true,
    requiredForEveryScene: true,
    uniqueAudioRequired: true,
    audioUrlMustBeReadable: true,
    metadataField: "audioMetadata",
    fallbackMetadataField: "fallbackUsed",
    providerId: "qwen-tts",
    modelId: "qwen3-tts-flash",
    voiceId: "Serena",
    fallbackAllowed: false,
  },
  conversationContract: {
    textChatRequired: true,
    voiceInputRequired: true,
    asr: {
      providerId: "qwen-asr",
      modelId: "qwen3-asr-flash",
      fallbackAllowed: false,
    },
  },
  generation: {
    enableWebSearch: false,
    enableImageGeneration: false,
    enableVideoGeneration: false,
    enableTTS: true,
    agentMode: "generate",
    automaticRetries: 0,
    staleAfterMs: 1_800_000,
  },
} as const;

export const sampleTeacherIdentityFixture = {
  verified: true,
  agentId: "teacher-agent-sample",
  teacherProfile: sampleGenerationContractFixture.teacher.profile,
  voiceConfig: sampleGenerationContractFixture.teacher.voiceIdentity.voiceConfig,
  selectionId: "qwen-tts::Serena",
} as const;

export const sampleSpeechAudioFixture = {
  verified: true,
  speechActionCount: 10,
  verifiedAssetCount: 10,
  signals: [
    "scene:slide-1:action:speech-1:audio:audio-1:asset-probed",
    "scene:slide-2:action:speech-2:audio:audio-2:asset-probed",
    "scene:simulation-1:action:speech-3:audio:audio-3:asset-probed",
    "scene:game-1:action:speech-4:audio:audio-4:asset-probed",
    "scene:visualization-1:action:speech-5:audio:audio-5:asset-probed",
    "scene:interactive-2:action:speech-6:audio:audio-6:asset-probed",
    "scene:quiz-1:action:speech-7:audio:audio-7:asset-probed",
    "scene:slide-3:action:speech-8:audio:audio-8:asset-probed",
    "scene:interactive-3:action:speech-9:audio:audio-9:asset-probed",
    "scene:recap-1:action:speech-10:audio:audio-10:asset-probed",
  ],
  providerId: "qwen-tts",
  modelId: "qwen3-tts-flash",
  voiceId: "Serena",
  fallbackAllowed: false,
} as const;

export const sampleSceneNarrationFixture = {
  verified: true,
  sceneCount: 10,
  narratedSceneCount: 10,
  transcriptSceneCount: 10,
  signals: Array.from({ length: 10 }, (_item, index) => `scene:${index + 1}:narration:transcript-verified`),
} as const;

export const sampleConversationFixture = {
  verified: true,
  textChat: true,
  voiceInput: true,
  asr: {
    providerId: "qwen-asr",
    modelId: "qwen3-asr-flash",
    fallbackAllowed: false,
  },
  signals: ["student-authenticated-text-chat", "student-microphone-qwen-asr"],
} as const;

const allRuntimeFeatures = [
  "slides",
  "quiz",
  "video",
  "3d_visualization",
  "simulation",
  "diagram",
  "code",
  "html_game",
  "pbl",
  "multi_agent_roundtable",
  "realtime_whiteboard",
  "teacher_actions",
  "mp4_export",
] as const;

const sampleRequiredFeatures = sampleGenerationContractFixture.requiredClassroom.features;

export const sampleRuntimeEvidenceFixture = Object.fromEntries(
  allRuntimeFeatures.map((feature) => {
    const verified = sampleRequiredFeatures.some((required) => required === feature);
    return [
      feature,
      {
        verified,
        signals: verified ? [`scene:sample:${feature}`] : [],
        reasons: verified ? [] : ["not_verified"],
      },
    ];
  }),
);

export const sampleRuntimeLaunchFixture = {
  ok: true,
  mode: "openmaic_full_runtime",
  launchUrl: "https://classroom.mira.test/mira/launch?ticket=sample-one-time",
  expiresAt: 1_787_000_000_000,
  assessmentAuthority: "mira_backend",
  features: {
    schemaVersion: "mira.openmaic.runtime-features.v2",
    sourceVersion: "openmaic@1.0.0",
    sourceCommit: "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5",
    enabled: sampleRequiredFeatures,
    requested: sampleRequiredFeatures,
    required: sampleRequiredFeatures,
    present: sampleRequiredFeatures,
    missing: [],
    evidence: sampleRuntimeEvidenceFixture,
    platform: {
      mp4Export: false,
      mp4ExportConfigured: false,
      mp4ExportCapabilityProbed: false,
      mp4ExportClassroomDryRun: false,
      assessmentAuthority: "mira_backend",
    },
    sceneTypes: ["slide", "quiz", "interactive"],
    actionTypes: ["speech", "discussion", "widget_action"],
    sceneCount: 10,
    generationContract: sampleGenerationContractFixture,
    teacherIdentity: sampleTeacherIdentityFixture,
    speechAudio: sampleSpeechAudioFixture,
    sceneNarration: sampleSceneNarrationFixture,
    conversation: sampleConversationFixture,
  },
} as const;

const formalMathTeacher = {
  profileId: "mira_math_clear",
  profileHash: "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
  teacherName: "小数老师",
  profileAvatar: "/teachers/ashu-math-v1.png",
  runtimeAvatar: "/avatars/teacher.png",
  gender: "male",
  voiceId: "Ethan",
  languageCode: "zh-CN",
} as const;

const formalRuntimeClassroomContractFixture = {
  schemaVersion: "mira.openmaic.formal-runtime.v1",
  exactSceneCount: 10,
  orderedSceneTypes: [
    "slide", "slide", "slide", "slide", "slide",
    "quiz", "quiz", "interactive", "interactive", "interactive",
  ],
  sceneDistribution: { slide: 5, quiz: 2, interactive: 3 },
  roster: { teacherCount: 1, peerCount: 4 },
  speechRequiredForEveryScene: true,
  distinctPeerDiscussions: 2,
  teacherEvidence: ["spotlight", "widget_highlight"],
  interactive: {
    requiredWidgetTypes: ["simulation", "game", "visualization3d"],
    widgetConfigRequired: true,
    productiveScriptRequired: true,
    noopRejected: true,
    fake3dRejected: true,
  },
  whiteboardRequired: false,
} as const;

const formalQuestionIds = ["q1", "q2", "q3", "q4", "q5"] as const;
const formalSourceCourseContentSha256 = "8".repeat(64);

export const formalRuntimeLaunchFixture = {
  ok: true,
  mode: "openmaic_full_runtime",
  launchUrl: "https://classroom.mira.test/mira/launch?ticket=formal-one-time",
  expiresAt: 1_787_000_000_000,
  assessmentAuthority: "mira_backend",
  features: {
    schemaVersion: "mira.openmaic.runtime-features.v2",
    sourceVersion: "openmaic@1.0.0",
    sourceCommit: "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5",
    enabled: sampleRequiredFeatures,
    requested: sampleRequiredFeatures,
    required: sampleRequiredFeatures,
    present: sampleRequiredFeatures,
    missing: [],
    evidence: sampleRuntimeEvidenceFixture,
    platform: {
      mp4Export: false,
      mp4ExportConfigured: false,
      mp4ExportCapabilityProbed: false,
      mp4ExportClassroomDryRun: false,
      assessmentAuthority: "mira_backend",
    },
    sceneTypes: ["slide", "quiz", "interactive"],
    actionTypes: ["speech", "discussion", "widget_action"],
    sceneCount: 10,
    generationContract: {
      schemaVersion: "mira.openmaic.formal-runtime.v1",
      authority: "mira_backend_formal_candidate",
      buildItemId: "formal-math-item",
      course: {
        id: "formal-math-course",
        version: "course-version-1",
        packageId: "formal-math-package",
        packageVersion: 1,
      },
      targetFingerprint: "a".repeat(64),
      runtimeRequestId: "formal-math-runtime-request",
      coursewareAuthority: {
        schemaVersion: "mira.openmaic.courseware-authority.v1",
        generationOwner: "openmaic",
        providerInvocation: "courseware_generation_only",
        classroomCompilation: "deterministic_no_llm",
        backendProviderCredentialsAccepted: false,
      },
      sourceCourseContentSha256: formalSourceCourseContentSha256,
      teachingBriefSha256: "9".repeat(64),
      teachingBrief: {
        schemaVersion: "mira.learning.formal-runtime-teaching-brief.v1",
        sourceCourseContentSha256: formalSourceCourseContentSha256,
        course: {
          id: "formal-math-course",
          version: "course-version-1",
          gradeCode: "primary_3",
          subject: "math",
          skillId: "math-skill",
          title: "数学正式课",
          objective: "数学正式课目标",
        },
        lesson: {
          intro: "今天一起学习新知识。",
          estimatedMinutes: 10,
          teachingFlow: {
            schemaVersion: "mira.learning.teaching-flow.v1",
            teach: {
              title: "先理解",
              sayText: "跟着老师一步一步学习。",
              keyPoints: ["先观察，再回答"],
            },
            demoQuestionId: "q1",
            guidedQuestionIds: ["q2", "q3"],
            independentQuestionIds: ["q4", "q5"],
            recap: { sayText: "我们完成了今天的学习。" },
          },
          questions: formalQuestionIds.map((id) => ({
            id,
            type: "numeric",
            prompt: `${id}题目`,
            skill: "math-skill",
            hint: `${id}提示`,
            explanation: `${id}讲解`,
          })),
        },
        authority: {
          source: "locked_learning_course",
          answerContractProvided: false,
          scoringRulesProvided: false,
          providerSecretsProvided: false,
        },
      },
      teacher: {
        teacherProfile: {
          id: formalMathTeacher.profileId,
          version: 2,
          contentHash: formalMathTeacher.profileHash,
          displayName: formalMathTeacher.teacherName,
          avatarPath: formalMathTeacher.profileAvatar,
        },
        runtime: {
          name: formalMathTeacher.teacherName,
          role: "teacher",
          avatar: formalMathTeacher.runtimeAvatar,
          teacherGender: formalMathTeacher.gender,
          voiceGender: formalMathTeacher.gender,
          voiceConfig: {
            providerId: "qwen-tts",
            modelId: "qwen3-tts-flash",
            voiceId: formalMathTeacher.voiceId,
          },
        },
      },
      requiredClassroom: formalRuntimeClassroomContractFixture,
      generation: {
        mode: "deterministic_no_llm",
        enableWebSearch: false,
        enableImageGeneration: false,
        enableVideoGeneration: false,
        enableTTS: false,
        agentMode: "generate",
        providerCalls: 0,
        automaticRetries: 0,
        maximumAttempts: 1,
      },
    },
    formalRuntimeContract: formalRuntimeClassroomContractFixture,
    formalEvidence: {
      sceneDistribution: { slide: 5, quiz: 2, interactive: 3 },
      peerCount: 4,
      speechSceneCount: 10,
      distinctDiscussionPeerCount: 2,
      spotlightVerified: true,
      widgetHighlightVerified: true,
      widgetTypes: ["game", "simulation", "visualization3d"],
      runtimeEventAuthority: {
        schemaVersion: "mira.openmaic.runtime-event-authority.v1",
        scenes: Array.from({ length: 10 }, (_item, sceneIndex) => ({
          sceneIndex,
          sceneId: `scene-${sceneIndex}`,
          completionActionId: `scene-${sceneIndex}-complete`,
          questionIds: sceneIndex === 5
            ? ["q2", "q3"]
            : sceneIndex === 6
              ? ["q4", "q5"]
              : [],
        })),
      },
      assessmentQuestionIds: ["q2", "q3", "q4", "q5"],
      teacher: {
        agentId: "formal-math-teacher",
        name: formalMathTeacher.teacherName,
        avatar: formalMathTeacher.runtimeAvatar,
        teacherGender: formalMathTeacher.gender,
        voiceGender: formalMathTeacher.gender,
        voiceId: formalMathTeacher.voiceId,
      },
    },
    classroomContentSha256: "7".repeat(64),
    teacherIdentity: {
      verified: true,
      agentId: "formal-math-teacher",
      subject: "math",
      avatarPath: formalMathTeacher.profileAvatar,
      runtimeAvatar: formalMathTeacher.runtimeAvatar,
      schemaVersion: "mira.openmaic.formal-subject-qwen3-voice.v1",
      teacherProfile: {
        id: formalMathTeacher.profileId,
        version: 2,
        contentHash: formalMathTeacher.profileHash,
      },
      teacherName: formalMathTeacher.teacherName,
      teacherGender: formalMathTeacher.gender,
      voiceGender: formalMathTeacher.gender,
      voiceId: formalMathTeacher.voiceId,
      languageCode: formalMathTeacher.languageCode,
      tts: {
        providerId: "qwen-tts",
        modelId: "qwen3-tts-flash",
        fallbackAllowed: false,
      },
      asr: {
        providerId: "qwen-asr",
        modelId: "qwen3-asr-flash",
        fallbackAllowed: false,
      },
    },
  },
} as const;
