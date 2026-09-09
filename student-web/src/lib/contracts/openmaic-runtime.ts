import { z } from "zod";
import { gradeBoundarySchema, imagePolicySchema, videoPolicySchema, skillPolicySchema,
  teachingQualityPolicySchema, professionalEvidenceExtensions, teachingQualityEvidenceSchema,
  imageReceiptSchema, videoReceiptSchema, imageEvidenceSchema, videoEvidenceSchema,
} from "./openmaic-professional-evidence";

export const openMaicRuntimeFeatureSchema = z.enum([
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
]);

export const openMaicRuntimeManifestV1Schema = z.object({
  schemaVersion: z.literal("mira.openmaic.runtime-features.v1"),
  sourceVersion: z.string().min(1),
  sourceCommit: z.string().regex(/^[0-9a-f]{40}$/),
  requested: z.array(openMaicRuntimeFeatureSchema),
  present: z.array(openMaicRuntimeFeatureSchema),
  platform: z.object({
    mp4Export: z.boolean(),
    assessmentAuthority: z.literal("mira_backend"),
  }).strict(),
  sceneTypes: z.array(z.string().min(1)).optional(),
  actionTypes: z.array(z.string().min(1)).optional(),
  sceneCount: z.number().int().positive().optional(),
}).strict();

const openMaicRuntimeEvidenceItemSchema = z.object({
  verified: z.boolean(),
  signals: z.array(z.string().min(1)),
  reasons: z.array(z.string().min(1)),
}).strict();

const openMaicQwenVoiceConfigSchema = z.object({
  providerId: z.literal("qwen-tts"),
  modelId: z.literal("qwen3-tts-flash"),
  voiceId: z.literal("Serena"),
}).strict();

const openMaicSampleTeacherProfileSchema = z.object({
  id: z.literal("mira_math_clear"),
  version: z.literal(2),
  displayName: z.literal("小数老师"),
  languageCode: z.literal("zh-CN"),
  teachingStyle: z.literal("clear_structured"),
}).strict();

const openMaicSampleVoiceIdentitySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.qwen3-voice.v1"),
  teacherProfile: z.object({
    id: z.literal("mira_math_clear"),
    version: z.literal(2),
  }).strict(),
  voiceConfig: openMaicQwenVoiceConfigSchema,
  selectionId: z.literal("qwen-tts::Serena"),
  displayName: z.literal("苏瑶 (Serena)"),
  languageCode: z.literal("zh-CN"),
}).strict();

export const openMaicSampleGenerationContractSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.sample-classroom.v2"),
  sampleMode: z.literal("primary_1_math_number_sense_20_v1"),
  authority: z.object({
    courseContext: z.literal("mira_active_catalog_release"),
    studentContext: z.literal("authenticated_learning_session"),
    clientOverridesAllowed: z.literal(false),
  }).strict(),
  course: z.object({
    id: z.string().min(1),
    version: z.string().min(1),
    releaseId: z.string().min(1),
    packageId: z.string().min(1),
    packageVersion: z.number().int().positive(),
    gradeCode: z.literal("primary_1"),
    gradeLabel: z.literal("小学一年级"),
    subjectCode: z.literal("math"),
    subjectLabel: z.literal("数学"),
    skill: z.object({
      gradeCode: z.literal("primary_1"),
      subject: z.literal("math"),
      curriculumVersion: z.literal("mira.primary.2026-fall.v1"),
      boundaryVersion: z.string().startsWith("mira.primary.2026-fall.v1:number_sense_20:"),
      skillId: z.literal("number_sense_20"),
      skillTitle: z.literal("20以内数感"),
      learningObjectives: z.tuple([
        z.literal("比较20以内数的大小"),
        z.literal("理解数的组成与顺序"),
      ]),
      allowedContent: z.tuple([
        z.literal("数数"),
        z.literal("数位雏形"),
        z.literal("大小比较"),
      ]),
      excludedContent: z.tuple([
        z.literal("负数"),
        z.literal("乘除法"),
        z.literal("分数"),
        z.literal("小数"),
      ]),
      prerequisiteSkills: z.tuple([]),
      language: z.literal("zh-CN"),
      estimatedMinutes: z.literal(10),
    }).strict(),
    title: z.string().min(1),
    objective: z.string().min(1),
  }).strict(),
  learnerConstraints: z.object({
    developmentStage: z.literal("early_primary_grade_1"),
    recommendedAgeBand: z.literal("6-8"),
    language: z.literal("zh-CN"),
    durationMinutes: z.literal(10),
    reading: z.literal("短句、口语化指令、一次只要求一个动作"),
    visuals: z.literal("用可数物和数轴支持20以内数量、顺序和大小比较"),
    prohibitedContent: z.tuple([
      z.literal("负数"),
      z.literal("乘除法"),
      z.literal("分数"),
      z.literal("小数"),
    ]),
  }).strict(),
  teacher: z.object({
    profile: openMaicSampleTeacherProfileSchema,
    voiceIdentity: openMaicSampleVoiceIdentitySchema,
  }).strict(),
  requiredClassroom: z.object({
    features: z.tuple([
      z.literal("slides"),
      z.literal("quiz"),
      z.literal("simulation"),
      z.literal("html_game"),
      z.literal("3d_visualization"),
      z.literal("multi_agent_roundtable"),
      z.literal("teacher_actions"),
    ]),
    exactSceneCount: z.literal(10),
    minimumSlideScenes: z.literal(2),
    sceneTypes: z.tuple([
      z.literal("slide"),
      z.literal("quiz"),
      z.literal("interactive"),
    ]),
    interactive: z.object({
      requiredWidgetTypes: z.tuple([
        z.literal("simulation"),
        z.literal("game"),
        z.literal("visualization3d"),
      ]),
      widgetOutlineRequired: z.literal(true),
      embeddedHtmlRequired: z.literal(true),
      controlsRequired: z.literal(true),
    }).strict(),
    multiAgent: z.object({
      teacherRequired: z.literal(true),
      minimumPeerAgents: z.literal(3),
      minimumDiscussionActions: z.literal(2),
      distinctPeerDiscussionsRequired: z.literal(true),
    }).strict(),
    teacherActionsRequired: z.literal(true),
    narration: z.object({
      requiredForEveryScene: z.literal(true),
      transcriptRequired: z.literal(true),
    }).strict(),
  }).strict(),
  speechAudioContract: z.object({
    schemaVersion: z.literal("mira.openmaic.speech-audio.v1"),
    requiredForEverySpeechAction: z.literal(true),
    requiredForEveryScene: z.literal(true),
    uniqueAudioRequired: z.literal(true),
    audioUrlMustBeReadable: z.literal(true),
    metadataField: z.literal("audioMetadata"),
    fallbackMetadataField: z.literal("fallbackUsed"),
    providerId: z.literal("qwen-tts"),
    modelId: z.literal("qwen3-tts-flash"),
    voiceId: z.literal("Serena"),
    fallbackAllowed: z.literal(false),
  }).strict(),
  conversationContract: z.object({
    textChatRequired: z.literal(true),
    voiceInputRequired: z.literal(true),
    asr: z.object({
      providerId: z.literal("qwen-asr"),
      modelId: z.literal("qwen3-asr-flash"),
      fallbackAllowed: z.literal(false),
    }).strict(),
  }).strict(),
  generation: z.object({
    enableWebSearch: z.literal(false),
    enableImageGeneration: z.literal(false),
    enableVideoGeneration: z.literal(false),
    enableTTS: z.literal(true),
    agentMode: z.literal("generate"),
    automaticRetries: z.literal(0),
    staleAfterMs: z.literal(1_800_000),
  }).strict(),
}).strict();

const openMaicSampleTeacherIdentitySchema = z.object({
  verified: z.literal(true),
  agentId: z.string().min(1),
  teacherProfile: openMaicSampleTeacherProfileSchema,
  voiceConfig: openMaicQwenVoiceConfigSchema,
  selectionId: z.literal("qwen-tts::Serena"),
}).strict();

const openMaicSampleSpeechAudioSchema = z.object({
  verified: z.literal(true),
  speechActionCount: z.number().int().positive(),
  verifiedAssetCount: z.number().int().positive(),
  signals: z.array(z.string().trim().min(1)).min(1).max(100),
  providerId: z.literal("qwen-tts"),
  modelId: z.literal("qwen3-tts-flash"),
  voiceId: z.literal("Serena"),
  fallbackAllowed: z.literal(false),
}).strict();

const openMaicSampleSceneNarrationSchema = z.object({
  verified: z.literal(true),
  sceneCount: z.literal(10),
  narratedSceneCount: z.literal(10),
  transcriptSceneCount: z.literal(10),
  signals: z.array(z.string().trim().min(1)).min(10).max(100),
}).strict();

const openMaicSampleConversationSchema = z.object({
  verified: z.literal(true),
  textChat: z.literal(true),
  voiceInput: z.literal(true),
  asr: z.object({
    providerId: z.literal("qwen-asr"),
    modelId: z.literal("qwen3-asr-flash"),
    fallbackAllowed: z.literal(false),
  }).strict(),
  signals: z.array(z.string().trim().min(1)).min(1).max(100),
}).strict();

export const openMaicRuntimeManifestV2Schema = z.object({
  schemaVersion: z.literal("mira.openmaic.runtime-features.v2"),
  sourceVersion: z.string().min(1),
  sourceCommit: z.string().regex(/^[0-9a-f]{40}$/),
  enabled: z.array(openMaicRuntimeFeatureSchema),
  requested: z.array(openMaicRuntimeFeatureSchema),
  required: z.array(openMaicRuntimeFeatureSchema),
  present: z.array(openMaicRuntimeFeatureSchema),
  missing: z.array(openMaicRuntimeFeatureSchema),
  evidence: z.record(openMaicRuntimeFeatureSchema, openMaicRuntimeEvidenceItemSchema),
  platform: z.object({
    mp4Export: z.boolean(),
    mp4ExportConfigured: z.boolean(),
    mp4ExportCapabilityProbed: z.boolean(),
    mp4ExportClassroomDryRun: z.boolean(),
    assessmentAuthority: z.literal("mira_backend"),
  }).strict(),
  sceneTypes: z.array(z.string().min(1)),
  actionTypes: z.array(z.string().min(1)),
  sceneCount: z.number().int().positive(),
  generationContract: openMaicSampleGenerationContractSchema.optional(),
  teacherIdentity: openMaicSampleTeacherIdentitySchema.optional(),
  speechAudio: openMaicSampleSpeechAudioSchema.optional(),
  sceneNarration: openMaicSampleSceneNarrationSchema.optional(),
  conversation: openMaicSampleConversationSchema.optional(),
}).strict().superRefine((manifest, context) => {
  const sampleFields = [
    manifest.generationContract,
    manifest.teacherIdentity,
    manifest.speechAudio,
    manifest.sceneNarration,
    manifest.conversation,
  ];
  const presentCount = sampleFields.filter((field) => field !== undefined).length;
  if (presentCount !== 0 && presentCount !== sampleFields.length) {
    context.addIssue({
      code: "custom",
      path: ["generationContract"],
      message: "样板完整课堂必须同时提供生成合同、老师音色和正式语音验证",
    });
  }
  if (manifest.generationContract) {
    const requiredFeatures = manifest.generationContract.requiredClassroom.features;
    const complete = manifest.missing.length === 0
      && requiredFeatures.every((feature) => manifest.required.includes(feature))
      && requiredFeatures.every((feature) => manifest.present.includes(feature))
      && requiredFeatures.every((feature) => manifest.evidence[feature]?.verified === true);
    if (!complete) {
      context.addIssue({
        code: "custom",
        path: ["present"],
        message: "样板完整课堂的全部必需能力必须通过证据检查",
      });
    }
  }
});

const openMaicSampleRequiredFeatures = [
  "slides",
  "quiz",
  "simulation",
  "html_game",
  "3d_visualization",
  "multi_agent_roundtable",
  "teacher_actions",
] as const;

export const openMaicSampleRuntimeManifestV2Schema = z.intersection(
  openMaicRuntimeManifestV2Schema,
  z.object({
    schemaVersion: z.literal("mira.openmaic.runtime-features.v2"),
    generationContract: openMaicSampleGenerationContractSchema,
    teacherIdentity: openMaicSampleTeacherIdentitySchema,
    speechAudio: openMaicSampleSpeechAudioSchema,
    sceneNarration: openMaicSampleSceneNarrationSchema,
    conversation: openMaicSampleConversationSchema,
  }),
).superRefine((manifest, context) => {
  const expected = new Set<string>(openMaicSampleRequiredFeatures);
  const hasExactFeatures = [manifest.enabled, manifest.requested, manifest.required]
    .every((features) => (
      features.length === expected.size
      && features.every((feature) => expected.has(feature))
    ));
  const hasVerifiedEvidence = openMaicSampleRequiredFeatures.every((feature) => (
    manifest.present.includes(feature)
    && manifest.evidence[feature]?.verified === true
  ));
  const hasCompleteSpeechAssets = (
    manifest.speechAudio.verifiedAssetCount === manifest.speechAudio.speechActionCount
  );
  const expectedSceneCount = manifest.generationContract.requiredClassroom.exactSceneCount;
  const hasEverySceneNarrated = (
    manifest.sceneCount === expectedSceneCount
    && manifest.sceneNarration.sceneCount === expectedSceneCount
    && manifest.sceneNarration.narratedSceneCount === expectedSceneCount
    && manifest.sceneNarration.transcriptSceneCount === expectedSceneCount
    && manifest.speechAudio.speechActionCount >= expectedSceneCount
  );
  if (
    !hasExactFeatures
    || manifest.missing.length !== 0
    || !hasVerifiedEvidence
    || !hasCompleteSpeechAssets
    || !hasEverySceneNarrated
  ) {
    context.addIssue({
      code: "custom",
      path: ["required"],
      message: "学生样板课堂必须完整核验固定能力与每条正式语音资产",
    });
  }
});

const openMaicFormalSubjectSchema = z.enum(["chinese", "math", "english"]);
const openMaicFormalSha256Schema = z.string().regex(/^[0-9a-f]{64}$/);

const openMaicFormalTeacherSpecs = {
  chinese: {
    subject: "chinese",
    profileId: "mira_chinese_gentle",
    profileHash: "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
    teacherName: "小语老师",
    profileAvatar: "/teachers/mi-chinese-v1.png",
    runtimeAvatar: "/avatars/teacher-2.png",
    gender: "female",
    voiceId: "Serena",
    languageCode: "zh-CN",
  },
  math: {
    subject: "math",
    profileId: "mira_math_clear",
    profileHash: "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
    teacherName: "小数老师",
    profileAvatar: "/teachers/ashu-math-v1.png",
    runtimeAvatar: "/avatars/teacher.png",
    gender: "male",
    voiceId: "Ethan",
    languageCode: "zh-CN",
  },
  english: {
    subject: "english",
    profileId: "mira_english_standard",
    profileHash: "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
    teacherName: "Mia 老师",
    profileAvatar: "/teachers/coco-english-v1.png",
    runtimeAvatar: "/avatars/teacher-2.png",
    gender: "female",
    voiceId: "Jennifer",
    languageCode: "en-US",
  },
} as const;

type OpenMaicFormalTeacherSpec = (typeof openMaicFormalTeacherSpecs)[keyof typeof openMaicFormalTeacherSpecs];

const formalTeacherGenerationBinding = <Spec extends OpenMaicFormalTeacherSpec>(identity: Spec) => z.object({
  teacherProfile: z.object({
    id: z.literal(identity.profileId),
    version: z.literal(2),
    contentHash: z.literal(identity.profileHash),
    displayName: z.literal(identity.teacherName),
    avatarPath: z.literal(identity.profileAvatar),
  }).strict(),
  runtime: z.object({
    name: z.literal(identity.teacherName),
    role: z.literal("teacher"),
    avatar: z.literal(identity.runtimeAvatar),
    teacherGender: z.literal(identity.gender),
    voiceGender: z.literal(identity.gender),
    voiceConfig: z.object({
      providerId: z.literal("qwen-tts"),
      modelId: z.literal("qwen3-tts-flash"),
      voiceId: z.literal(identity.voiceId),
    }).strict(),
  }).strict(),
}).strict();

const openMaicFormalTeacherGenerationBindingSchema = z.union([
  formalTeacherGenerationBinding(openMaicFormalTeacherSpecs.chinese),
  formalTeacherGenerationBinding(openMaicFormalTeacherSpecs.math),
  formalTeacherGenerationBinding(openMaicFormalTeacherSpecs.english),
]);

const formalTeacherEvidence = <Spec extends OpenMaicFormalTeacherSpec>(identity: Spec) => z.object({
  agentId: z.string().trim().min(1).max(160),
  name: z.literal(identity.teacherName),
  avatar: z.literal(identity.runtimeAvatar),
  teacherGender: z.literal(identity.gender),
  voiceGender: z.literal(identity.gender),
  voiceId: z.literal(identity.voiceId),
}).strict();

const openMaicFormalTeacherEvidenceSchema = z.union([
  formalTeacherEvidence(openMaicFormalTeacherSpecs.chinese),
  formalTeacherEvidence(openMaicFormalTeacherSpecs.math),
  formalTeacherEvidence(openMaicFormalTeacherSpecs.english),
]);

const openMaicFormalRuntimeClassroomContractSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.formal-runtime.v1"),
  exactSceneCount: z.literal(10),
  orderedSceneTypes: z.tuple([
    z.literal("slide"),
    z.literal("slide"),
    z.literal("slide"),
    z.literal("slide"),
    z.literal("slide"),
    z.literal("quiz"),
    z.literal("quiz"),
    z.literal("interactive"),
    z.literal("interactive"),
    z.literal("interactive"),
  ]),
  sceneDistribution: z.object({
    slide: z.literal(5),
    quiz: z.literal(2),
    interactive: z.literal(3),
  }).strict(),
  roster: z.object({
    teacherCount: z.literal(1),
    peerCount: z.literal(4),
  }).strict(),
  speechRequiredForEveryScene: z.literal(true),
  distinctPeerDiscussions: z.literal(2),
  teacherEvidence: z.tuple([
    z.literal("spotlight"),
    z.literal("widget_highlight"),
  ]),
  interactive: z.object({
    requiredWidgetTypes: z.tuple([
      z.literal("simulation"),
      z.literal("game"),
      z.literal("visualization3d"),
    ]),
    widgetConfigRequired: z.literal(true),
    productiveScriptRequired: z.literal(true),
    noopRejected: z.literal(true),
    fake3dRejected: z.literal(true),
  }).strict(),
  whiteboardRequired: z.literal(false),
}).strict();

const openMaicAdaptiveSceneTypeSchema = z.enum([
  "slide",
  "quiz",
  "interactive",
  "pbl",
]);

const openMaicAdaptiveWidgetTypeSchema = z.enum([
  "simulation",
  "diagram",
  "code",
  "game",
  "visualization3d",
]);

export const openMaicAdaptiveFormalRuntimeClassroomContractSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.formal-runtime.v4-deepseek-professional"),
  scenePlanning: z.object({
    mode: z.literal("adaptive"),
    authority: z.literal("openmaic_professional_agent"),
    exactCountRequired: z.literal(false),
    allowedSceneTypes: z.tuple([
      z.literal("slide"),
      z.literal("quiz"),
      z.literal("interactive"),
      z.literal("pbl"),
    ]),
    requiredSceneTypes: z.tuple([
      z.literal("slide"),
      z.literal("quiz"),
      z.literal("interactive"),
    ]),
    defaultDurationMinutes: z.object({
      min: z.literal(15),
      max: z.literal(30),
    }).strict(),
    scenesPerMinute: z.object({
      min: z.literal(1),
      max: z.literal(2),
    }).strict(),
    maxSceneCount: z.literal(60),
  }).strict(),
  roster: z.object({
    teacherCount: z.literal(1),
    peerCount: z.literal(4),
  }).strict(),
  speechRequiredForEveryScene: z.literal(true),
  speechActions: z.object({
    perScene: z.object({
      min: z.literal(1),
      max: z.literal(20),
    }).strict(),
    total: z.object({
      min: z.literal(1),
      max: z.literal(240),
    }).strict(),
    interactiveSpotlightRequired: z.literal(false),
  }).strict(),
  slideSpotlight: z.object({
    minimumPerSlide: z.literal(1),
    targetMustBeRenderable: z.literal(true),
    focusExplanationSequenceRequired: z.literal(true),
    consecutiveSpotlightsAllowed: z.literal(true),
  }).strict(),
  distinctPeerDiscussions: z.literal(2),
  teacherEvidence: z.tuple([
    z.literal("spotlight"),
    z.literal("widget_highlight"),
  ]),
  interactive: z.object({
    allowedWidgetTypes: z.tuple([
      z.literal("simulation"),
      z.literal("diagram"),
      z.literal("code"),
      z.literal("game"),
      z.literal("visualization3d"),
    ]),
    widgetConfigRequired: z.literal(true),
    productiveScriptRequired: z.literal(true),
    noopRejected: z.literal(true),
    fake3dRejected: z.literal(true),
  }).strict(),
  whiteboardRequired: z.literal(false),
}).strict();

const openMaicFormalQuestionSchema = z.object({
  id: z.string().trim().min(1).max(160),
  type: z.string().trim().min(1).max(32),
  prompt: z.string().trim().min(1).max(1200),
  skill: z.string().trim().min(1).max(240),
  hint: z.string().trim().min(1).max(800),
  explanation: z.string().trim().min(1).max(1600),
  choices: z.array(z.object({
    id: z.string().trim().min(1).max(80),
    label: z.string().trim().min(1).max(480),
  }).strict()).min(1).max(32).optional(),
}).strict();

const openMaicFormalTeachingBriefSchema = z.object({
  schemaVersion: z.literal("mira.learning.formal-runtime-teaching-brief.v1"),
  sourceCourseContentSha256: openMaicFormalSha256Schema,
  course: z.object({
    id: z.string().trim().min(1).max(255),
    version: z.string().trim().min(1).max(64),
    gradeCode: z.string().regex(/^primary_[1-6]$/),
    subject: openMaicFormalSubjectSchema,
    skillId: z.string().trim().min(1).max(120),
    title: z.string().trim().min(1).max(160),
    objective: z.string().trim().min(1).max(600),
  }).strict(),
  lesson: z.object({
    intro: z.string().trim().min(1).max(1200),
    estimatedMinutes: z.number().int().min(5).max(30),
    teachingFlow: z.object({
      schemaVersion: z.literal("mira.learning.teaching-flow.v1"),
      teach: z.object({
        title: z.string().trim().min(1).max(320),
        sayText: z.string().trim().min(1).max(2400),
        keyPoints: z.array(z.string().trim().min(1).max(400)).min(1).max(3),
      }).strict(),
      demoQuestionId: z.string().trim().min(1).max(160),
      guidedQuestionIds: z.tuple([
        z.string().trim().min(1).max(160),
        z.string().trim().min(1).max(160),
      ]),
      independentQuestionIds: z.tuple([
        z.string().trim().min(1).max(160),
        z.string().trim().min(1).max(160),
      ]),
      recap: z.object({
        sayText: z.string().trim().min(1).max(1200),
      }).strict(),
    }).strict(),
    questions: z.array(openMaicFormalQuestionSchema).length(5),
  }).strict(),
  authority: z.object({
    source: z.literal("locked_learning_course"),
    answerContractProvided: z.literal(false),
    scoringRulesProvided: z.literal(false),
    providerSecretsProvided: z.literal(false),
  }).strict(),
}).strict().superRefine((brief, context) => {
  const questionIds = brief.lesson.questions.map((question) => question.id);
  const flow = brief.lesson.teachingFlow;
  const flowIds = [
    flow.demoQuestionId,
    ...flow.guidedQuestionIds,
    ...flow.independentQuestionIds,
  ];
  if (
    new Set(questionIds).size !== 5
    || questionIds.some((questionId, index) => questionId !== flowIds[index])
  ) {
    context.addIssue({
      code: "custom",
      path: ["lesson", "teachingFlow"],
      message: "正式课堂教学流程必须逐一绑定五道服务端题目",
    });
  }
});

const openMaicCoursewareAuthoritySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.courseware-authority.v1"),
  generationOwner: z.literal("openmaic"),
  providerInvocation: z.literal("courseware_generation_only"),
  classroomCompilation: z.literal("deterministic_no_llm"),
  backendProviderCredentialsAccepted: z.literal(false),
}).strict();

const openMaicProfessionalCoursewareAuthoritySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.courseware-authority.v2-professional"),
  generationOwner: z.literal("openmaic"),
  providerInvocation: z.literal("professional_agent"),
  classroomCompilation: z.literal("professional_skill_workflow"),
  backendProviderCredentialsAccepted: z.literal(false),
}).strict();

const openMaicProfessionalCreationPolicySchema = z.object({
  image: imagePolicySchema.optional(), video: videoPolicySchema.optional(),
  skillOrchestration: skillPolicySchema.optional(), teachingQuality: teachingQualityPolicySchema.optional(),
  schemaVersion: z.literal("mira.openmaic.professional-creation.v1"),
  mode: z.literal("professional_skill"),
  workflowVersion: z.literal("openmaic-pro-agent.v1"),
  skillId: z.literal("mira-primary-courseware"),
  supportingSkillIds: z.tuple([
    z.literal("k12-core-literacy-planning"),
    z.literal("deep-interactive"),
  ]),
  userPromptRequired: z.literal(false),
  webSearch: z.object({
    enabled: z.literal(true),
    providerManaged: z.literal(true),
    maxCalls: z.literal(4),
    citationsRequired: z.literal(true),
    primarySourcesPreferred: z.literal(true),
    minimumFetchedSources: z.literal(1),
  }).strict(),
  studentToolsEnabled: z.literal(false),
}).strict();

const openMaicProfessionalGenerationOptionsSchema = z.object({
  mode: z.literal("professional_skill"),
  workflowVersion: z.literal("openmaic-pro-agent.v1"),
  skillId: z.literal("mira-primary-courseware"),
  supportingSkillIds: z.tuple([
    z.literal("k12-core-literacy-planning"),
    z.literal("deep-interactive"),
  ]),
  userPromptRequired: z.literal(false),
  enableWebSearch: z.literal(true),
  webSearchRequired: z.literal(true),
  enableImageGeneration: z.boolean(),
  enableVideoGeneration: z.boolean(),
  enableTTS: z.literal(false),
  agentMode: z.literal("generate"),
  providerInvocation: z.literal("openmaic_agent_managed"),
  automaticRetries: z.literal(0),
  maximumAttempts: z.literal(1),
}).strict();

const openMaicRuntimeEventAuthoritySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.runtime-event-authority.v1"),
  scenes: z.array(z.object({
    sceneIndex: z.number().int().min(0).max(9),
    sceneId: z.string().trim().min(1).max(255),
    completionActionId: z.string().trim().min(1).max(255),
    questionIds: z.array(z.string().trim().min(1).max(160)).max(5),
  }).strict()).length(10),
}).strict();

const openMaicAdaptiveRuntimeEventAuthoritySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.runtime-event-authority.v1"),
  scenes: z.array(z.object({
    sceneIndex: z.number().int().min(0).max(59),
    sceneId: z.string().trim().min(1).max(255),
    completionActionId: z.string().trim().min(1).max(255),
    questionIds: z.array(z.string().trim().min(1).max(160)).max(5),
  }).strict()).min(1).max(60),
}).strict().superRefine((authority, context) => {
  if (authority.scenes.some((scene, index) => scene.sceneIndex !== index)) {
    context.addIssue({
      code: "custom",
      path: ["scenes"],
      message: "正式课堂运行事件必须按实际场景从零连续排列",
    });
  }
});

const openMaicFormalGenerationContractSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.formal-runtime.v1"),
  authority: z.literal("mira_backend_formal_candidate"),
  buildItemId: z.string().trim().min(1).max(128),
  course: z.object({
    id: z.string().trim().min(1).max(255),
    version: z.string().trim().min(1).max(64),
    packageId: z.string().trim().min(1).max(128),
    packageVersion: z.number().int().positive(),
  }).strict(),
  targetFingerprint: openMaicFormalSha256Schema,
  runtimeRequestId: z.string().trim().min(1).max(128),
  coursewareAuthority: openMaicCoursewareAuthoritySchema,
  sourceCourseContentSha256: openMaicFormalSha256Schema,
  teachingBriefSha256: openMaicFormalSha256Schema,
  teachingBrief: openMaicFormalTeachingBriefSchema,
  teacher: openMaicFormalTeacherGenerationBindingSchema,
  requiredClassroom: openMaicFormalRuntimeClassroomContractSchema,
  generation: z.object({
    mode: z.literal("deterministic_no_llm"),
    enableWebSearch: z.literal(false),
    enableImageGeneration: z.literal(false),
    enableVideoGeneration: z.literal(false),
    enableTTS: z.literal(false),
    agentMode: z.literal("generate"),
    providerCalls: z.literal(0),
    automaticRetries: z.literal(0),
    maximumAttempts: z.literal(1),
  }).strict(),
}).strict().superRefine((contract, context) => {
  const brief = contract.teachingBrief;
  if (
    contract.course.id !== brief.course.id
    || contract.course.version !== brief.course.version
    || contract.sourceCourseContentSha256 !== brief.sourceCourseContentSha256
  ) {
    context.addIssue({
      code: "custom",
      path: ["teachingBrief"],
      message: "正式课堂生成合同必须绑定同一课程版本与内容摘要",
    });
  }
});

export const openMaicAdaptiveFormalGenerationContractSchema = z.object({
  gradeBoundary: gradeBoundarySchema.optional(), gradeBoundarySha256: openMaicFormalSha256Schema.optional(),
  schemaVersion: z.literal("mira.openmaic.formal-runtime.v4-deepseek-professional"),
  authority: z.literal("mira_backend_formal_candidate"),
  buildItemId: z.string().trim().min(1).max(128),
  course: z.object({
    id: z.string().trim().min(1).max(255),
    version: z.string().trim().min(1).max(64),
    packageId: z.string().trim().min(1).max(128),
    packageVersion: z.number().int().positive(),
  }).strict(),
  targetFingerprint: openMaicFormalSha256Schema,
  runtimeRequestId: z.string().trim().min(1).max(128),
  coursewareAuthority: openMaicProfessionalCoursewareAuthoritySchema,
  professionalCreationPolicy: openMaicProfessionalCreationPolicySchema,
  sourceCourseContentSha256: openMaicFormalSha256Schema,
  teachingBriefSha256: openMaicFormalSha256Schema,
  teachingBrief: openMaicFormalTeachingBriefSchema,
  teacher: openMaicFormalTeacherGenerationBindingSchema,
  requiredClassroom: openMaicAdaptiveFormalRuntimeClassroomContractSchema,
  generation: openMaicProfessionalGenerationOptionsSchema,
}).strict().superRefine((contract, context) => {
  const brief = contract.teachingBrief;
  if (contract.generation.enableImageGeneration !== Boolean(contract.professionalCreationPolicy.image)
      || contract.generation.enableVideoGeneration !== Boolean(contract.professionalCreationPolicy.video)
      || Boolean(contract.professionalCreationPolicy.teachingQuality) !== Boolean(contract.gradeBoundary && contract.gradeBoundarySha256)
      || Boolean(contract.professionalCreationPolicy.skillOrchestration) !== Boolean(contract.gradeBoundary)) {
    context.addIssue({ code: "custom", path: ["professionalCreationPolicy"], message: "专业课堂扩展策略必须与生成选项和年级边界同时提供" });
  }
  if (
    contract.course.id !== brief.course.id
    || contract.course.version !== brief.course.version
    || contract.sourceCourseContentSha256 !== brief.sourceCourseContentSha256
  ) {
    context.addIssue({
      code: "custom",
      path: ["teachingBrief"],
      message: "专业课堂生成合同必须绑定同一课程版本与内容摘要",
    });
  }
});

const formalTeacherIdentity = <Spec extends OpenMaicFormalTeacherSpec>(identity: Spec) => z.object({
  verified: z.literal(true),
  agentId: z.string().trim().min(1).max(160),
  subject: z.literal(identity.subject),
  avatarPath: z.literal(identity.profileAvatar),
  runtimeAvatar: z.literal(identity.runtimeAvatar),
  schemaVersion: z.literal("mira.openmaic.formal-subject-qwen3-voice.v1"),
  teacherProfile: z.object({
    id: z.literal(identity.profileId),
    version: z.literal(2),
    contentHash: z.literal(identity.profileHash),
  }).strict(),
  teacherName: z.literal(identity.teacherName),
  teacherGender: z.literal(identity.gender),
  voiceGender: z.literal(identity.gender),
  voiceId: z.literal(identity.voiceId),
  languageCode: z.literal(identity.languageCode),
  tts: z.object({
    providerId: z.literal("qwen-tts"),
    modelId: z.literal("qwen3-tts-flash"),
    fallbackAllowed: z.literal(false),
  }).strict(),
  asr: z.object({
    providerId: z.literal("qwen-asr"),
    modelId: z.literal("qwen3-asr-flash"),
    fallbackAllowed: z.literal(false),
  }).strict(),
}).strict();

export const openMaicFormalTeacherIdentitySchema = z.union([
  formalTeacherIdentity(openMaicFormalTeacherSpecs.chinese),
  formalTeacherIdentity(openMaicFormalTeacherSpecs.math),
  formalTeacherIdentity(openMaicFormalTeacherSpecs.english),
]);

const openMaicProfessionalCreationReceiptSchema = z.object({
  ...professionalEvidenceExtensions,
  schemaVersion: z.literal("mira.openmaic.professional-creation-receipt.v1"),
  status: z.literal("succeeded"),
  runtimeRequestId: z.string().trim().min(1).max(128),
  buildItemId: z.string().trim().min(1).max(128),
  classroomId: z.string().trim().min(1).max(255),
  teachingBriefSha256: openMaicFormalSha256Schema,
  sessionId: z.string().trim().min(1).max(128),
  workflowVersion: z.literal("openmaic-pro-agent.v1"),
  skillId: z.literal("mira-primary-courseware"),
  supportingSkillIds: z.tuple([
    z.literal("k12-core-literacy-planning"),
    z.literal("deep-interactive"),
  ]),
  userPromptRequired: z.literal(false),
  studentToolsEnabled: z.literal(false),
  webSearchEnabled: z.literal(true),
  receiptSha256: openMaicFormalSha256Schema,
}).strict();

const openMaicProfessionalResearchReceiptSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.professional-research-receipt.v1"),
  status: z.literal("succeeded"),
  runtimeRequestId: z.string().trim().min(1).max(128),
  buildItemId: z.string().trim().min(1).max(128),
  classroomId: z.string().trim().min(1).max(255),
  sessionId: z.string().trim().min(1).max(128),
  providerId: z.string().trim().min(1).max(64),
  searchCount: z.number().int().min(1).max(4),
  resultCount: z.number().int().positive(),
  fetchedSourceCount: z.number().int().positive(),
  citationCount: z.number().int().positive(),
  searches: z.array(z.object({
    query: z.string().trim().min(1).max(512),
    searchedAt: z.string().trim().min(1).max(64),
    resultCount: z.number().int().positive(),
  }).strict()).min(1).max(4),
  sources: z.array(z.object({
    title: z.string().trim().min(1).max(512),
    url: z.string().url().max(2_048),
    textSha256: openMaicFormalSha256Schema,
  }).strict()).min(1),
  citations: z.array(z.object({
    url: z.string().url().max(2_048),
    sceneIds: z.array(z.string().trim().min(1).max(128)).min(1).max(60),
  }).strict()).min(1),
  receiptSha256: openMaicFormalSha256Schema,
}).strict().superRefine((receipt, context) => {
  if (
    receipt.searches.length !== receipt.searchCount
    || receipt.sources.length !== receipt.fetchedSourceCount
    || receipt.citations.length !== receipt.citationCount
    || receipt.resultCount < receipt.sources.length
  ) {
    context.addIssue({
      code: "custom",
      path: ["searchCount"],
      message: "联网研究回执的搜索、材料与引用计数必须一致",
    });
  }
  const sourceUrls = new Set(receipt.sources.map((source) => source.url));
  if (receipt.citations.some((citation) => !sourceUrls.has(citation.url))) {
    context.addIssue({
      code: "custom",
      path: ["citations"],
      message: "联网研究引用必须来自已核验材料",
    });
  }
});

const openMaicProfessionalCreationEvidenceSchema = z.object({
  ...professionalEvidenceExtensions,
  verified: z.literal(true),
  schemaVersion: z.literal("mira.openmaic.professional-creation-receipt.v1"),
  sessionId: z.string().trim().min(1).max(128),
  workflowVersion: z.literal("openmaic-pro-agent.v1"),
  skillId: z.literal("mira-primary-courseware"),
  supportingSkillIds: z.tuple([
    z.literal("k12-core-literacy-planning"),
    z.literal("deep-interactive"),
  ]),
  userPromptRequired: z.literal(false),
  studentToolsEnabled: z.literal(false),
  webSearchEnabled: z.literal(true),
  receiptSha256: openMaicFormalSha256Schema,
}).strict();

const openMaicProfessionalResearchEvidenceSchema = z.object({
  verified: z.literal(true),
  schemaVersion: z.literal("mira.openmaic.professional-research-receipt.v1"),
  sessionId: z.string().trim().min(1).max(128),
  providerId: z.string().trim().min(1).max(64),
  searchCount: z.number().int().min(1).max(4),
  resultCount: z.number().int().positive(),
  fetchedSourceCount: z.number().int().positive(),
  citationCount: z.number().int().positive(),
  citedSceneCount: z.number().int().positive().max(60),
  receiptSha256: openMaicFormalSha256Schema,
}).strict();

const openMaicAdaptiveFeatureListSchema = z.array(openMaicRuntimeFeatureSchema)
  .min(1)
  .max(openMaicRuntimeFeatureSchema.options.length)
  .superRefine((features, context) => {
    if (new Set(features).size !== features.length) {
      context.addIssue({
        code: "custom",
        message: "正式课堂能力列表不能包含重复项",
      });
    }
  });

const openMaicAdaptiveSceneTypeListSchema = z.array(openMaicAdaptiveSceneTypeSchema)
  .min(1)
  .max(openMaicAdaptiveSceneTypeSchema.options.length)
  .superRefine((sceneTypes, context) => {
    if (new Set(sceneTypes).size !== sceneTypes.length) {
      context.addIssue({
        code: "custom",
        message: "正式课堂场景类型列表不能包含重复项",
      });
    }
  });

export const openMaicFormalRuntimeManifestV2Schema = z.object({
  schemaVersion: z.literal("mira.openmaic.runtime-features.v2"),
  sourceVersion: z.string().min(1),
  sourceCommit: z.string().regex(/^[0-9a-f]{40}$/),
  enabled: z.array(openMaicRuntimeFeatureSchema),
  requested: z.array(openMaicRuntimeFeatureSchema),
  required: z.array(openMaicRuntimeFeatureSchema),
  present: z.array(openMaicRuntimeFeatureSchema),
  missing: z.array(openMaicRuntimeFeatureSchema),
  evidence: z.record(openMaicRuntimeFeatureSchema, openMaicRuntimeEvidenceItemSchema),
  platform: z.object({
    mp4Export: z.boolean(),
    mp4ExportConfigured: z.boolean(),
    mp4ExportCapabilityProbed: z.boolean(),
    mp4ExportClassroomDryRun: z.boolean(),
    assessmentAuthority: z.literal("mira_backend"),
  }).strict(),
  sceneTypes: z.array(z.string().min(1)),
  actionTypes: z.array(z.string().min(1)),
  sceneCount: z.literal(10),
  generationContract: openMaicFormalGenerationContractSchema,
  formalRuntimeContract: openMaicFormalRuntimeClassroomContractSchema,
  formalEvidence: z.object({
    sceneDistribution: z.object({
      slide: z.literal(5),
      quiz: z.literal(2),
      interactive: z.literal(3),
    }).strict(),
    peerCount: z.literal(4),
    speechSceneCount: z.literal(10),
    distinctDiscussionPeerCount: z.number().int().min(2).max(4),
    spotlightVerified: z.literal(true),
    widgetHighlightVerified: z.literal(true),
    widgetTypes: z.tuple([
      z.literal("game"),
      z.literal("simulation"),
      z.literal("visualization3d"),
    ]),
    runtimeEventAuthority: openMaicRuntimeEventAuthoritySchema,
    assessmentQuestionIds: z.array(z.string().trim().min(1).max(160)).length(4),
    teacher: openMaicFormalTeacherEvidenceSchema,
  }).strict(),
  classroomContentSha256: openMaicFormalSha256Schema,
  teacherIdentity: openMaicFormalTeacherIdentitySchema,
}).strict().superRefine((manifest, context) => {
  const required = new Set<string>(openMaicSampleRequiredFeatures);
  const hasExactFeatures = [manifest.enabled, manifest.requested, manifest.required]
    .every((features) => (
      features.length === required.size
      && features.every((feature) => required.has(feature))
    ));
  const hasVerifiedEvidence = openMaicSampleRequiredFeatures.every((feature) => (
    manifest.present.includes(feature)
    && manifest.evidence[feature]?.verified === true
  ));
  const course = manifest.generationContract.teachingBrief.course;
  const identity = manifest.teacherIdentity;
  const generationTeacher = manifest.generationContract.teacher;
  const generationProfile = generationTeacher.teacherProfile;
  const generationRuntime = generationTeacher.runtime;
  const evidenceTeacher = manifest.formalEvidence.teacher;
  const teachingFlow = manifest.generationContract.teachingBrief.lesson.teachingFlow;
  const expectedAssessmentQuestionIds = [
    ...teachingFlow.guidedQuestionIds,
    ...teachingFlow.independentQuestionIds,
  ];
  const assessmentQuestionIds = manifest.formalEvidence.assessmentQuestionIds;
  const runtimeEventScenes = manifest.formalEvidence.runtimeEventAuthority.scenes;
  const runtimeEventQuestionIds = runtimeEventScenes.flatMap((scene) => scene.questionIds);
  const hasExactAssessmentAuthority = (
    assessmentQuestionIds.every((questionId, index) => (
      questionId === expectedAssessmentQuestionIds[index]
    ))
    && runtimeEventQuestionIds.length === expectedAssessmentQuestionIds.length
    && runtimeEventQuestionIds.every((questionId, index) => (
      questionId === expectedAssessmentQuestionIds[index]
    ))
    && runtimeEventScenes.every((scene, index) => scene.sceneIndex === index)
  );
  const hasExactTeacherBinding = (
    course.subject === identity.subject
    && generationProfile.id === identity.teacherProfile.id
    && generationProfile.version === identity.teacherProfile.version
    && generationProfile.contentHash === identity.teacherProfile.contentHash
    && generationProfile.displayName === identity.teacherName
    && generationProfile.avatarPath === identity.avatarPath
    && generationRuntime.name === identity.teacherName
    && generationRuntime.avatar === identity.runtimeAvatar
    && generationRuntime.teacherGender === identity.teacherGender
    && generationRuntime.voiceGender === identity.voiceGender
    && generationRuntime.voiceConfig.voiceId === identity.voiceId
    && evidenceTeacher.agentId === identity.agentId
    && evidenceTeacher.name === identity.teacherName
    && evidenceTeacher.avatar === identity.runtimeAvatar
    && evidenceTeacher.teacherGender === identity.teacherGender
    && evidenceTeacher.voiceGender === identity.voiceGender
    && evidenceTeacher.voiceId === identity.voiceId
  );
  if (
    !hasExactFeatures
    || manifest.missing.length !== 0
    || !hasVerifiedEvidence
    || !hasExactTeacherBinding
  ) {
    context.addIssue({
      code: "custom",
      path: ["teacherIdentity"],
      message: "正式课堂的课程、学科和冻结老师音色必须由服务端合同一致绑定",
    });
  }
  if (!hasExactAssessmentAuthority) {
    context.addIssue({
      code: "custom",
      path: ["formalEvidence", "runtimeEventAuthority"],
      message: "正式课堂运行事件与服务端评分题目必须逐一绑定",
    });
  }
});

export const openMaicAdaptiveFormalRuntimeManifestV2Schema = z.object({
  media: imageReceiptSchema.optional(), video: videoReceiptSchema.optional(),
  schemaVersion: z.literal("mira.openmaic.runtime-features.v2"),
  sourceVersion: z.string().min(1),
  sourceCommit: z.string().regex(/^[0-9a-f]{40}$/),
  enabled: openMaicAdaptiveFeatureListSchema,
  requested: openMaicAdaptiveFeatureListSchema,
  required: openMaicAdaptiveFeatureListSchema,
  present: openMaicAdaptiveFeatureListSchema,
  missing: z.tuple([]),
  evidence: z.record(openMaicRuntimeFeatureSchema, openMaicRuntimeEvidenceItemSchema),
  platform: z.object({
    mp4Export: z.boolean(),
    mp4ExportConfigured: z.boolean(),
    mp4ExportCapabilityProbed: z.boolean(),
    mp4ExportClassroomDryRun: z.boolean(),
    assessmentAuthority: z.literal("mira_backend"),
  }).strict(),
  sceneTypes: openMaicAdaptiveSceneTypeListSchema,
  actionTypes: z.array(z.string().trim().min(1).max(80)).min(1),
  sceneCount: z.number().int().min(1).max(60),
  generationContract: openMaicAdaptiveFormalGenerationContractSchema,
  formalRuntimeContract: openMaicAdaptiveFormalRuntimeClassroomContractSchema,
  formalEvidence: z.object({
    media: imageEvidenceSchema.optional(), video: videoEvidenceSchema.optional(),
    teachingQuality: teachingQualityEvidenceSchema.optional(),
    sceneDistribution: z.object({
      slide: z.number().int().min(1).max(60),
      quiz: z.number().int().min(1).max(60),
      interactive: z.number().int().min(1).max(60),
      pbl: z.number().int().min(0).max(60),
    }).strict(),
    peerCount: z.literal(4),
    speechSceneCount: z.number().int().min(1).max(60),
    speechActionCount: z.number().int().min(1).max(240),
    discussionActionCount: z.number().int().nonnegative().optional(),
    teacherActionCount: z.number().int().nonnegative().optional(),
    distinctDiscussionPeerCount: z.number().int().min(2).max(4),
    spotlightVerified: z.literal(true),
    widgetHighlightVerified: z.literal(true),
    widgetTypes: z.array(openMaicAdaptiveWidgetTypeSchema).min(1).max(5),
    runtimeEventAuthority: openMaicAdaptiveRuntimeEventAuthoritySchema,
    assessmentQuestionIds: z.array(z.string().trim().min(1).max(160)).length(4),
    teacher: openMaicFormalTeacherEvidenceSchema,
    professionalCreation: openMaicProfessionalCreationEvidenceSchema,
    research: openMaicProfessionalResearchEvidenceSchema,
  }).strict(),
  professionalCreation: openMaicProfessionalCreationReceiptSchema,
  research: openMaicProfessionalResearchReceiptSchema,
  sourceCourseContentSha256: openMaicFormalSha256Schema,
  teachingBriefSha256: openMaicFormalSha256Schema,
  classroomContentSha256: openMaicFormalSha256Schema,
  teacherIdentity: openMaicFormalTeacherIdentitySchema,
}).strict().superRefine((manifest, context) => {
  const generation = manifest.generationContract;
  const brief = generation.teachingBrief;
  const course = brief.course;
  const identity = manifest.teacherIdentity;
  const generationTeacher = generation.teacher;
  const generationProfile = generationTeacher.teacherProfile;
  const generationRuntime = generationTeacher.runtime;
  const formalEvidence = manifest.formalEvidence;
  const evidenceTeacher = formalEvidence.teacher;
  const distribution = formalEvidence.sceneDistribution;
  const professionalReceipt = manifest.professionalCreation;
  const extended = generation.professionalCreationPolicy;
  const quality = professionalReceipt.teachingQuality;
  const skills = professionalReceipt.skillOrchestration;
  if (extended.teachingQuality || extended.skillOrchestration) {
    const qualityEvidence = formalEvidence.teachingQuality;
    const boundary = generation.gradeBoundary;
    if (!quality || !skills || !qualityEvidence || !boundary
        || quality.stageId !== professionalReceipt.classroomId
        || quality.sessionId !== professionalReceipt.sessionId
        || quality.teachingBriefSha256 !== generation.teachingBriefSha256
        || quality.gradeBoundarySha256 !== generation.gradeBoundarySha256
        || skills.selectionPlan.gradeBoundarySha256 !== generation.gradeBoundarySha256
        || quality.selectionPlanSha256 !== skills.selectionPlan.planSha256
        || quality.receiptSha256 !== qualityEvidence.receiptSha256
        || quality.snapshotSha256 !== qualityEvidence.snapshotSha256
        || quality.receiptSha256 !== formalEvidence.professionalCreation.teachingQuality?.receiptSha256
        || skills.receiptSha256 !== formalEvidence.professionalCreation.skillOrchestration?.receiptSha256
        || quality.sceneHashes.length !== manifest.sceneCount
        || qualityEvidence.sceneHashes.length !== manifest.sceneCount
        || boundary.gradeCode !== course.gradeCode || boundary.subject !== course.subject || boundary.skillId !== course.skillId
        || quality.review.objectives.length !== boundary.learningObjectives.length
        || quality.review.objectives.some((o, i) => o.objectiveIndex !== i)
        || quality.sceneHashes.some((s, i) => s.sceneId !== formalEvidence.runtimeEventAuthority.scenes[i]?.sceneId
          || s.sceneId !== qualityEvidence.sceneHashes[i]?.sceneId || s.sceneSha256 !== qualityEvidence.sceneHashes[i]?.sceneSha256)) {
      context.addIssue({ code: "custom", path: ["professionalCreation", "teachingQuality"],
        message: "教学审核、技能选择、年级边界与当前课堂必须完整匹配" });
    }
  }
  for (const kind of ["image", "video"] as const) {
    const receipt = kind === "image" ? manifest.media : manifest.video;
    const proof = kind === "image" ? formalEvidence.media : formalEvidence.video;
    const enabled = kind === "image" ? professionalReceipt.imageGenerationEnabled : professionalReceipt.videoGenerationEnabled;
    const evidenceEnabled = kind === "image" ? formalEvidence.professionalCreation.imageGenerationEnabled : formalEvidence.professionalCreation.videoGenerationEnabled;
    const policyId = kind === "image" ? professionalReceipt.imagePolicyId : professionalReceipt.videoPolicyId;
    const evidencePolicyId = kind === "image" ? formalEvidence.professionalCreation.imagePolicyId : formalEvidence.professionalCreation.videoPolicyId;
    if (extended[kind] || receipt || proof || enabled || evidenceEnabled) {
      const assetCount = receipt && ("imageCount" in receipt ? receipt.imageCount : receipt.videoCount);
      if (!extended[kind] || !receipt || !proof || !enabled || !evidenceEnabled
          || policyId !== extended[kind].policyId || evidencePolicyId !== policyId
          || receipt.runtimeRequestId !== generation.runtimeRequestId || receipt.buildItemId !== generation.buildItemId
          || receipt.classroomId !== professionalReceipt.classroomId || receipt.sessionId !== professionalReceipt.sessionId
          || receipt.receiptSha256 !== proof.receiptSha256 || assetCount !== proof.verifiedAssetCount
          || assetCount !== ("imageCount" in proof ? proof.imageCount : proof.videoCount)
          || receipt.assets.some(a => !a.src.startsWith(`/api/classroom-media/${receipt.classroomId}/media/`)
            || a.sceneIds.some(sceneId => !formalEvidence.runtimeEventAuthority.scenes.some(s => s.sceneId === sceneId)))) {
        context.addIssue({ code: "custom", path: [kind], message: "媒体生成策略、素材和当前课堂发布证据必须一致" });
      }
    }
  }
  const runtimeEventScenes = formalEvidence.runtimeEventAuthority.scenes;
  const teachingFlow = brief.lesson.teachingFlow;
  const expectedAssessmentQuestionIds = [
    ...teachingFlow.guidedQuestionIds,
    ...teachingFlow.independentQuestionIds,
  ];
  const runtimeEventQuestionIds = runtimeEventScenes.flatMap((scene) => scene.questionIds);

  const distributionTotal = Object.values(distribution).reduce(
    (total, count) => total + count,
    0,
  );
  const expectedSceneTypes = (Object.entries(distribution) as Array<[
    z.infer<typeof openMaicAdaptiveSceneTypeSchema>,
    number,
  ]>)
    .filter(([, count]) => count > 0)
    .map(([sceneType]) => sceneType);
  const actualSceneTypes = new Set(manifest.sceneTypes);
  if (
    distributionTotal !== manifest.sceneCount
    || formalEvidence.speechSceneCount !== manifest.sceneCount
    || formalEvidence.speechActionCount < manifest.sceneCount
    || formalEvidence.speechActionCount > manifest.sceneCount * 20
    || runtimeEventScenes.length !== manifest.sceneCount
    || expectedSceneTypes.length !== actualSceneTypes.size
    || expectedSceneTypes.some((sceneType) => !actualSceneTypes.has(sceneType))
  ) {
    context.addIssue({
      code: "custom",
      path: ["formalEvidence", "sceneDistribution"],
      message: "专业课堂的场景分布、讲解和运行事件必须与实际场景总数一致",
    });
  }

  const widgetTypes = formalEvidence.widgetTypes;
  if (
    new Set(widgetTypes).size !== widgetTypes.length
    || widgetTypes.some((widgetType, index) => (
      index > 0 && widgetTypes[index - 1].localeCompare(widgetType) >= 0
    ))
  ) {
    context.addIssue({
      code: "custom",
      path: ["formalEvidence", "widgetTypes"],
      message: "专业课堂互动组件必须是已排序且不重复的实际组件集合",
    });
  }

  const expectedRequiredFeatures: OpenMaicRuntimeFeature[] = [
    "slides",
    "quiz",
    "multi_agent_roundtable",
    "teacher_actions",
  ];
  const widgetFeature: Record<z.infer<typeof openMaicAdaptiveWidgetTypeSchema>, OpenMaicRuntimeFeature> = {
    simulation: "simulation",
    diagram: "diagram",
    code: "code",
    game: "html_game",
    visualization3d: "3d_visualization",
  };
  for (const widgetType of widgetTypes) {
    const feature = widgetFeature[widgetType];
    if (!expectedRequiredFeatures.includes(feature)) {
      expectedRequiredFeatures.push(feature);
    }
  }
  if (distribution.pbl > 0) {
    expectedRequiredFeatures.push("pbl");
  }
  const required = new Set(manifest.required);
  const exactRequiredFeatures = (
    required.size === expectedRequiredFeatures.length
    && expectedRequiredFeatures.every((feature) => required.has(feature))
  );
  const matchesRequired = [manifest.enabled, manifest.requested].every((features) => (
    features.length === required.size
    && features.every((feature) => required.has(feature))
  ));
  const requiredFeaturesVerified = expectedRequiredFeatures.every((feature) => (
    manifest.present.includes(feature)
    && manifest.evidence[feature]?.verified === true
  ));
  if (!exactRequiredFeatures || !matchesRequired || !requiredFeaturesVerified) {
    context.addIssue({
      code: "custom",
      path: ["required"],
      message: "专业课堂能力必须由核心能力与实际场景组件动态派生并通过证据核验",
    });
  }

  const requiredActions = ["speech", "discussion", "spotlight", "widget_highlight"];
  if (requiredActions.some((actionType) => !manifest.actionTypes.includes(actionType))) {
    context.addIssue({
      code: "custom",
      path: ["actionTypes"],
      message: "专业课堂缺少讲解、讨论、聚光或互动高亮动作",
    });
  }

  const hasExactAssessmentAuthority = (
    formalEvidence.assessmentQuestionIds.every((questionId, index) => (
      questionId === expectedAssessmentQuestionIds[index]
    ))
    && runtimeEventQuestionIds.length === expectedAssessmentQuestionIds.length
    && runtimeEventQuestionIds.every((questionId, index) => (
      questionId === expectedAssessmentQuestionIds[index]
    ))
  );
  const runtimeSceneIds = runtimeEventScenes.map((scene) => scene.sceneId);
  const runtimeCompletionActionIds = runtimeEventScenes.map(
    (scene) => scene.completionActionId,
  );
  if (
    !hasExactAssessmentAuthority
    || new Set(runtimeSceneIds).size !== runtimeSceneIds.length
    || new Set(runtimeCompletionActionIds).size !== runtimeCompletionActionIds.length
  ) {
    context.addIssue({
      code: "custom",
      path: ["formalEvidence", "runtimeEventAuthority"],
      message: "专业课堂运行事件与四道服务端评分题必须逐一绑定",
    });
  }

  const hasExactTeacherBinding = (
    course.subject === identity.subject
    && generationProfile.id === identity.teacherProfile.id
    && generationProfile.version === identity.teacherProfile.version
    && generationProfile.contentHash === identity.teacherProfile.contentHash
    && generationProfile.displayName === identity.teacherName
    && generationProfile.avatarPath === identity.avatarPath
    && generationRuntime.name === identity.teacherName
    && generationRuntime.avatar === identity.runtimeAvatar
    && generationRuntime.teacherGender === identity.teacherGender
    && generationRuntime.voiceGender === identity.voiceGender
    && generationRuntime.voiceConfig.voiceId === identity.voiceId
    && evidenceTeacher.agentId === identity.agentId
    && evidenceTeacher.name === identity.teacherName
    && evidenceTeacher.avatar === identity.runtimeAvatar
    && evidenceTeacher.teacherGender === identity.teacherGender
    && evidenceTeacher.voiceGender === identity.voiceGender
    && evidenceTeacher.voiceId === identity.voiceId
  );
  if (!hasExactTeacherBinding) {
    context.addIssue({
      code: "custom",
      path: ["teacherIdentity"],
      message: "专业课堂的课程、学科和冻结老师音色必须由服务端合同一致绑定",
    });
  }

  const professional = manifest.professionalCreation;
  const research = manifest.research;
  const professionalEvidence = formalEvidence.professionalCreation;
  const researchEvidence = formalEvidence.research;
  const citedSceneIds = new Set(research.citations.flatMap((citation) => citation.sceneIds));
  const runtimeSceneIdSet = new Set(runtimeSceneIds);
  const professionalReceiptsMatch = (
    professional.runtimeRequestId === generation.runtimeRequestId
    && professional.buildItemId === generation.buildItemId
    && professional.teachingBriefSha256 === manifest.teachingBriefSha256
    && research.runtimeRequestId === generation.runtimeRequestId
    && research.buildItemId === generation.buildItemId
    && research.classroomId === professional.classroomId
    && research.sessionId === professional.sessionId
    && professionalEvidence.schemaVersion === professional.schemaVersion
    && professionalEvidence.sessionId === professional.sessionId
    && professionalEvidence.receiptSha256 === professional.receiptSha256
    && researchEvidence.schemaVersion === research.schemaVersion
    && researchEvidence.sessionId === research.sessionId
    && researchEvidence.providerId === research.providerId
    && researchEvidence.searchCount === research.searchCount
    && researchEvidence.resultCount === research.resultCount
    && researchEvidence.fetchedSourceCount === research.fetchedSourceCount
    && researchEvidence.citationCount === research.citationCount
    && researchEvidence.citedSceneCount === citedSceneIds.size
    && researchEvidence.receiptSha256 === research.receiptSha256
    && [...citedSceneIds].every((sceneId) => runtimeSceneIdSet.has(sceneId))
  );
  if (!professionalReceiptsMatch) {
    context.addIssue({
      code: "custom",
      path: ["professionalCreation"],
      message: "专业创作与联网研究回执必须绑定同一课堂生成会话",
    });
  }

  if (
    manifest.sourceCourseContentSha256 !== generation.sourceCourseContentSha256
    || manifest.teachingBriefSha256 !== generation.teachingBriefSha256
  ) {
    context.addIssue({
      code: "custom",
      path: ["sourceCourseContentSha256"],
      message: "专业课堂必须保留生成合同中的课程内容与教学简报摘要",
    });
  }
});

export const openMaicRuntimeManifestSchema = z.union([
  openMaicRuntimeManifestV1Schema,
  openMaicRuntimeManifestV2Schema,
  openMaicFormalRuntimeManifestV2Schema,
  openMaicAdaptiveFormalRuntimeManifestV2Schema,
]);

const openMaicSampleRuntimeLaunchSchema = z.object({
  ok: z.literal(true),
  mode: z.literal("openmaic_full_runtime"),
  launchUrl: z.string().url(),
  expiresAt: z.number().int().positive(),
  features: openMaicSampleRuntimeManifestV2Schema,
  assessmentAuthority: z.literal("mira_backend"),
}).strict();

export const openMaicFormalRuntimeLaunchSchema = z.object({
  ok: z.literal(true),
  mode: z.literal("openmaic_full_runtime"),
  launchUrl: z.string().url(),
  expiresAt: z.number().int().positive(),
  features: z.union([
    openMaicFormalRuntimeManifestV2Schema,
    openMaicAdaptiveFormalRuntimeManifestV2Schema,
  ]),
  assessmentAuthority: z.literal("mira_backend"),
}).strict();

/**
 * Compatibility parser for retained sample and legacy payloads. It must never
 * authorize a student classroom launch; use openMaicFormalRuntimeLaunchSchema
 * at every student-entry boundary.
 */
export const openMaicRuntimeLaunchSchema = z.union([
  openMaicSampleRuntimeLaunchSchema,
  openMaicFormalRuntimeLaunchSchema,
]);

export type OpenMaicRuntimeFeature = z.infer<typeof openMaicRuntimeFeatureSchema>;
export type OpenMaicRuntimeManifest = z.infer<typeof openMaicRuntimeManifestSchema>;
export type OpenMaicFormalRuntimeLaunch = z.infer<typeof openMaicFormalRuntimeLaunchSchema>;
export type OpenMaicRuntimeLaunch = z.infer<typeof openMaicRuntimeLaunchSchema>;
