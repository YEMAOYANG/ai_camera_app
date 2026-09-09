import { describe, expect, it } from "vitest";

import {
  openMaicFormalRuntimeLaunchSchema,
  openMaicRuntimeLaunchSchema,
  openMaicRuntimeManifestSchema,
} from "@/lib/contracts/openmaic-runtime";
import {
  sampleConversationFixture,
  sampleGenerationContractFixture,
  sampleSceneNarrationFixture,
  sampleSpeechAudioFixture,
  sampleTeacherIdentityFixture,
} from "@/test/fixtures/openmaic-runtime";

const valid = {
  ok: true,
  mode: "openmaic_full_runtime",
  launchUrl: "https://classroom.mira.test/mira/launch?ticket=omt_safe",
  expiresAt: 1_787_000_000_000,
  assessmentAuthority: "mira_backend",
  features: {
    schemaVersion: "mira.openmaic.runtime-features.v1",
    sourceVersion: "openmaic@1.0.0",
    sourceCommit: "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5",
    requested: ["slides", "3d_visualization", "simulation", "html_game", "pbl", "multi_agent_roundtable", "realtime_whiteboard", "teacher_actions"],
    present: ["slides", "html_game", "pbl"],
    platform: { mp4Export: false, assessmentAuthority: "mira_backend" },
  },
};

const runtimeFeatures = [
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

const evidence = Object.fromEntries(runtimeFeatures.map((feature) => [
  feature,
  {
    verified: ["slides", "quiz", "html_game"].includes(feature),
    signals: feature === "slides" ? ["scene:slide-1:slide-elements:2"] : [],
    reasons: ["slides", "quiz", "html_game"].includes(feature) ? [] : ["not_verified"],
  },
]));

const validV2 = {
  ...valid,
  features: {
    schemaVersion: "mira.openmaic.runtime-features.v2",
    sourceVersion: "openmaic@1.0.0",
    sourceCommit: "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5",
    enabled: ["slides", "quiz", "html_game", "video"],
    requested: ["slides", "quiz", "html_game", "video"],
    required: ["slides", "html_game"],
    present: ["slides", "quiz", "html_game"],
    missing: [],
    evidence,
    platform: {
      mp4Export: false,
      mp4ExportConfigured: false,
      mp4ExportCapabilityProbed: false,
      mp4ExportClassroomDryRun: false,
      assessmentAuthority: "mira_backend",
    },
    sceneTypes: ["slide", "quiz", "interactive"],
    actionTypes: ["speech"],
    sceneCount: 3,
  },
};

const sampleRequiredFeatures = [
  "slides",
  "quiz",
  "simulation",
  "html_game",
  "3d_visualization",
  "multi_agent_roundtable",
  "teacher_actions",
] as const;

const sampleEvidence = Object.fromEntries(runtimeFeatures.map((feature) => [
  feature,
  {
    verified: sampleRequiredFeatures.includes(feature as typeof sampleRequiredFeatures[number]),
    signals: sampleRequiredFeatures.includes(feature as typeof sampleRequiredFeatures[number])
      ? [`scene:sample:${feature}`]
      : [],
    reasons: sampleRequiredFeatures.includes(feature as typeof sampleRequiredFeatures[number])
      ? []
      : ["not_verified"],
  },
]));

const validSampleV2 = {
  ...validV2,
  features: {
    ...validV2.features,
    enabled: sampleRequiredFeatures,
    requested: sampleRequiredFeatures,
    required: sampleRequiredFeatures,
    present: sampleRequiredFeatures,
    missing: [],
    evidence: sampleEvidence,
    sceneCount: 10,
    generationContract: sampleGenerationContractFixture,
    teacherIdentity: sampleTeacherIdentityFixture,
    speechAudio: sampleSpeechAudioFixture,
    sceneNarration: sampleSceneNarrationFixture,
    conversation: sampleConversationFixture,
  },
};

const formalTeacherIdentities = {
  chinese: {
    profileId: "mira_chinese_gentle",
    profileHash: "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
    teacherName: "小语老师",
    profileAvatar: "/teachers/mi-chinese-v1.png",
    runtimeAvatar: "/avatars/teacher-2.png",
    teacherGender: "female",
    voiceGender: "female",
    voiceId: "Serena",
    languageCode: "zh-CN",
  },
  math: {
    profileId: "mira_math_clear",
    profileHash: "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
    teacherName: "小数老师",
    profileAvatar: "/teachers/ashu-math-v1.png",
    runtimeAvatar: "/avatars/teacher.png",
    teacherGender: "male",
    voiceGender: "male",
    voiceId: "Ethan",
    languageCode: "zh-CN",
  },
  english: {
    profileId: "mira_english_standard",
    profileHash: "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
    teacherName: "Mia 老师",
    profileAvatar: "/teachers/coco-english-v1.png",
    runtimeAvatar: "/avatars/teacher-2.png",
    teacherGender: "female",
    voiceGender: "female",
    voiceId: "Jennifer",
    languageCode: "en-US",
  },
} as const;

const formalRuntimeClassroomContract = {
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

const adaptiveFormalRuntimeClassroomContract = {
  schemaVersion: "mira.openmaic.formal-runtime.v4-deepseek-professional",
  scenePlanning: {
    mode: "adaptive",
    authority: "openmaic_professional_agent",
    exactCountRequired: false,
    allowedSceneTypes: ["slide", "quiz", "interactive", "pbl"],
    requiredSceneTypes: ["slide", "quiz", "interactive"],
    defaultDurationMinutes: { min: 15, max: 30 },
    scenesPerMinute: { min: 1, max: 2 },
    maxSceneCount: 60,
  },
  roster: { teacherCount: 1, peerCount: 4 },
  speechRequiredForEveryScene: true,
  speechActions: {
    perScene: { min: 1, max: 20 },
    total: { min: 1, max: 240 },
    interactiveSpotlightRequired: false,
  },
  slideSpotlight: {
    minimumPerSlide: 1,
    targetMustBeRenderable: true,
    focusExplanationSequenceRequired: true,
    consecutiveSpotlightsAllowed: true,
  },
  distinctPeerDiscussions: 2,
  teacherEvidence: ["spotlight", "widget_highlight"],
  interactive: {
    allowedWidgetTypes: ["simulation", "diagram", "code", "game", "visualization3d"],
    widgetConfigRequired: true,
    productiveScriptRequired: true,
    noopRejected: true,
    fake3dRejected: true,
  },
  whiteboardRequired: false,
} as const;

function formalLaunch(subject: keyof typeof formalTeacherIdentities) {
  const identity = formalTeacherIdentities[subject];
  const questionIds = ["q1", "q2", "q3", "q4", "q5"] as const;
  const sourceCourseContentSha256 = "8".repeat(64);
  const runtimeEventScenes = Array.from({ length: 10 }, (_item, sceneIndex) => ({
    sceneIndex,
    sceneId: `scene-${sceneIndex}`,
    completionActionId: `scene-${sceneIndex}-complete`,
    questionIds: sceneIndex === 5
      ? ["q2", "q3"]
      : sceneIndex === 6
        ? ["q4", "q5"]
        : [],
  }));
  return {
    ...validV2,
    features: {
      ...validV2.features,
      enabled: sampleRequiredFeatures,
      requested: sampleRequiredFeatures,
      required: sampleRequiredFeatures,
      present: sampleRequiredFeatures,
      missing: [],
      evidence: sampleEvidence,
      sceneCount: 10,
      generationContract: {
        schemaVersion: "mira.openmaic.formal-runtime.v1",
        authority: "mira_backend_formal_candidate",
        buildItemId: `formal-${subject}-item`,
        course: {
          id: `formal-${subject}-course`,
          version: "course-version-1",
          packageId: `formal-${subject}-package`,
          packageVersion: 1,
        },
        targetFingerprint: "a".repeat(64),
        runtimeRequestId: `formal-${subject}-runtime-request`,
        coursewareAuthority: {
          schemaVersion: "mira.openmaic.courseware-authority.v1",
          generationOwner: "openmaic",
          providerInvocation: "courseware_generation_only",
          classroomCompilation: "deterministic_no_llm",
          backendProviderCredentialsAccepted: false,
        },
        sourceCourseContentSha256,
        teachingBriefSha256: "9".repeat(64),
        teachingBrief: {
          schemaVersion: "mira.learning.formal-runtime-teaching-brief.v1",
          sourceCourseContentSha256,
          course: {
            id: `formal-${subject}-course`,
            version: "course-version-1",
            gradeCode: "primary_3",
            subject,
            skillId: `${subject}-skill`,
            title: `${subject}正式课`,
            objective: `${subject}正式课目标`,
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
            questions: questionIds.map((id) => ({
              id,
              type: "numeric",
              prompt: `${id}题目`,
              skill: `${subject}-skill`,
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
            id: identity.profileId,
            version: 2,
            contentHash: identity.profileHash,
            displayName: identity.teacherName,
            avatarPath: identity.profileAvatar,
          },
          runtime: {
            name: identity.teacherName,
            role: "teacher",
            avatar: identity.runtimeAvatar,
            teacherGender: identity.teacherGender,
            voiceGender: identity.voiceGender,
            voiceConfig: {
              providerId: "qwen-tts",
              modelId: "qwen3-tts-flash",
              voiceId: identity.voiceId,
            },
          },
        },
        requiredClassroom: formalRuntimeClassroomContract,
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
      formalRuntimeContract: formalRuntimeClassroomContract,
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
          scenes: runtimeEventScenes,
        },
        assessmentQuestionIds: ["q2", "q3", "q4", "q5"],
        teacher: {
          agentId: `formal-${subject}-teacher`,
          name: identity.teacherName,
          avatar: identity.runtimeAvatar,
          teacherGender: identity.teacherGender,
          voiceGender: identity.voiceGender,
          voiceId: identity.voiceId,
        },
      },
      classroomContentSha256: "7".repeat(64),
      teacherIdentity: {
        verified: true,
        agentId: `formal-${subject}-teacher`,
        subject,
        avatarPath: identity.profileAvatar,
        runtimeAvatar: identity.runtimeAvatar,
        schemaVersion: "mira.openmaic.formal-subject-qwen3-voice.v1",
        teacherProfile: {
          id: identity.profileId,
          version: 2,
          contentHash: identity.profileHash,
        },
        teacherName: identity.teacherName,
        teacherGender: identity.teacherGender,
        voiceGender: identity.voiceGender,
        voiceId: identity.voiceId,
        languageCode: identity.languageCode,
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
  };
}

function adaptiveFormalLaunch(subject: keyof typeof formalTeacherIdentities) {
  const legacy = formalLaunch(subject);
  const sceneCount = 12;
  const sourceCourseContentSha256 = "8".repeat(64);
  const teachingBriefSha256 = "9".repeat(64);
  const runtimeRequestId = `adaptive-${subject}-runtime-request`;
  const buildItemId = `adaptive-${subject}-item`;
  const classroomId = `adaptive-${subject}-classroom`;
  const sessionId = `adaptive-${subject}-session`;
  const professionalReceiptSha256 = "5".repeat(64);
  const researchReceiptSha256 = "6".repeat(64);
  const requiredFeatures = [
    "slides",
    "quiz",
    "multi_agent_roundtable",
    "teacher_actions",
    "diagram",
    "html_game",
    "pbl",
  ] as const;
  const adaptiveEvidence = Object.fromEntries(runtimeFeatures.map((feature) => [
    feature,
    {
      verified: requiredFeatures.includes(feature as typeof requiredFeatures[number]),
      signals: requiredFeatures.includes(feature as typeof requiredFeatures[number])
        ? [`scene:adaptive:${feature}`]
        : [],
      reasons: requiredFeatures.includes(feature as typeof requiredFeatures[number])
        ? []
        : ["not_verified"],
    },
  ]));
  const runtimeEventScenes = Array.from({ length: sceneCount }, (_item, sceneIndex) => ({
    sceneIndex,
    sceneId: `adaptive-scene-${sceneIndex}`,
    completionActionId: `adaptive-scene-${sceneIndex}-complete`,
    questionIds: sceneIndex === 5
      ? ["q2", "q3"]
      : sceneIndex === 6
        ? ["q4", "q5"]
        : [],
  }));
  const professionalCreation = {
    schemaVersion: "mira.openmaic.professional-creation-receipt.v1",
    status: "succeeded",
    runtimeRequestId,
    buildItemId,
    classroomId,
    teachingBriefSha256,
    sessionId,
    workflowVersion: "openmaic-pro-agent.v1",
    skillId: "mira-primary-courseware",
    supportingSkillIds: ["k12-core-literacy-planning", "deep-interactive"],
    userPromptRequired: false,
    studentToolsEnabled: false,
    webSearchEnabled: true,
    receiptSha256: professionalReceiptSha256,
  } as const;
  const research = {
    schemaVersion: "mira.openmaic.professional-research-receipt.v1",
    status: "succeeded",
    runtimeRequestId,
    buildItemId,
    classroomId,
    sessionId,
    providerId: "cogevol_maas_search",
    searchCount: 1,
    resultCount: 2,
    fetchedSourceCount: 1,
    citationCount: 1,
    searches: [{
      query: `${subject} primary curriculum`,
      searchedAt: "2026-09-03T10:00:00Z",
      resultCount: 2,
    }],
    sources: [{
      title: "Primary curriculum source",
      url: "https://example.edu/primary-curriculum",
      textSha256: "4".repeat(64),
    }],
    citations: [{
      url: "https://example.edu/primary-curriculum",
      sceneIds: ["adaptive-scene-0"],
    }],
    receiptSha256: researchReceiptSha256,
  } as const;

  return {
    ...legacy,
    features: {
      ...legacy.features,
      enabled: requiredFeatures,
      requested: requiredFeatures,
      required: requiredFeatures,
      present: requiredFeatures,
      missing: [],
      evidence: adaptiveEvidence,
      sceneTypes: ["slide", "quiz", "interactive", "pbl"],
      actionTypes: ["discussion", "speech", "spotlight", "widget_highlight"],
      sceneCount,
      generationContract: {
        ...legacy.features.generationContract,
        schemaVersion: "mira.openmaic.formal-runtime.v4-deepseek-professional",
        buildItemId,
        runtimeRequestId,
        coursewareAuthority: {
          schemaVersion: "mira.openmaic.courseware-authority.v2-professional",
          generationOwner: "openmaic",
          providerInvocation: "professional_agent",
          classroomCompilation: "professional_skill_workflow",
          backendProviderCredentialsAccepted: false,
        },
        professionalCreationPolicy: {
          schemaVersion: "mira.openmaic.professional-creation.v1",
          mode: "professional_skill",
          workflowVersion: "openmaic-pro-agent.v1",
          skillId: "mira-primary-courseware",
          supportingSkillIds: ["k12-core-literacy-planning", "deep-interactive"],
          userPromptRequired: false,
          webSearch: {
            enabled: true,
            providerManaged: true,
            maxCalls: 4,
            citationsRequired: true,
            primarySourcesPreferred: true,
            minimumFetchedSources: 1,
          },
          studentToolsEnabled: false,
        },
        sourceCourseContentSha256,
        teachingBriefSha256,
        requiredClassroom: adaptiveFormalRuntimeClassroomContract,
        generation: {
          mode: "professional_skill",
          workflowVersion: "openmaic-pro-agent.v1",
          skillId: "mira-primary-courseware",
          supportingSkillIds: ["k12-core-literacy-planning", "deep-interactive"],
          userPromptRequired: false,
          enableWebSearch: true,
          webSearchRequired: true,
          enableImageGeneration: false,
          enableVideoGeneration: false,
          enableTTS: false,
          agentMode: "generate",
          providerInvocation: "openmaic_agent_managed",
          automaticRetries: 0,
          maximumAttempts: 1,
        },
      },
      formalRuntimeContract: adaptiveFormalRuntimeClassroomContract,
      formalEvidence: {
        sceneDistribution: { slide: 5, quiz: 2, interactive: 4, pbl: 1 },
        peerCount: 4,
        speechSceneCount: sceneCount,
        speechActionCount: 30,
        distinctDiscussionPeerCount: 2,
        spotlightVerified: true,
        widgetHighlightVerified: true,
        widgetTypes: ["diagram", "game"],
        runtimeEventAuthority: {
          schemaVersion: "mira.openmaic.runtime-event-authority.v1",
          scenes: runtimeEventScenes,
        },
        assessmentQuestionIds: ["q2", "q3", "q4", "q5"],
        teacher: legacy.features.formalEvidence.teacher,
        professionalCreation: {
          verified: true,
          schemaVersion: professionalCreation.schemaVersion,
          sessionId,
          workflowVersion: professionalCreation.workflowVersion,
          skillId: professionalCreation.skillId,
          supportingSkillIds: professionalCreation.supportingSkillIds,
          userPromptRequired: false,
          studentToolsEnabled: false,
          webSearchEnabled: true,
          receiptSha256: professionalReceiptSha256,
        },
        research: {
          verified: true,
          schemaVersion: research.schemaVersion,
          sessionId,
          providerId: research.providerId,
          searchCount: research.searchCount,
          resultCount: research.resultCount,
          fetchedSourceCount: research.fetchedSourceCount,
          citationCount: research.citationCount,
          citedSceneCount: 1,
          receiptSha256: researchReceiptSha256,
        },
      },
      professionalCreation,
      research,
      sourceCourseContentSha256,
      teachingBriefSha256,
      classroomContentSha256: "7".repeat(64),
    },
  };
}

describe("full OpenMAIC runtime contract", () => {
  it("keeps v1 readable as a generic manifest but rejects it as a student launch", () => {
    expect(openMaicRuntimeManifestSchema.parse(valid.features).present).toContain("pbl");
    expect(openMaicRuntimeLaunchSchema.safeParse(valid).success).toBe(false);
  });

  it("keeps evidence-only v2 readable generically but rejects it as a student launch", () => {
    const parsed = openMaicRuntimeManifestSchema.parse(validV2.features);
    expect(parsed.schemaVersion).toBe("mira.openmaic.runtime-features.v2");
    expect(parsed.present).not.toContain("video");
    expect(openMaicRuntimeLaunchSchema.safeParse(validV2).success).toBe(false);
  });

  it("keeps the verified stage-2 sample readable only through the compatibility launch parser", () => {
    const parsed = openMaicRuntimeLaunchSchema.parse(validSampleV2);
    expect(parsed.features.schemaVersion).toBe("mira.openmaic.runtime-features.v2");
    if (parsed.features.schemaVersion !== "mira.openmaic.runtime-features.v2") {
      throw new Error("expected v2 runtime manifest");
    }
    if (!("speechAudio" in parsed.features)) {
      throw new Error("expected the explicit legacy sample contract");
    }
    expect(parsed.features.speechAudio).toMatchObject({
      verified: true,
      speechActionCount: 10,
      verifiedAssetCount: 10,
      providerId: "qwen-tts",
      modelId: "qwen3-tts-flash",
      voiceId: "Serena",
      fallbackAllowed: false,
    });
    expect(parsed.features.teacherIdentity?.teacherProfile).toMatchObject({
      id: "mira_math_clear",
      version: 2,
    });
    expect(parsed.features.sceneNarration).toMatchObject({
      verified: true,
      sceneCount: 10,
      narratedSceneCount: 10,
      transcriptSceneCount: 10,
    });
    expect(parsed.features.conversation).toMatchObject({
      verified: true,
      textChat: true,
      voiceInput: true,
      asr: { providerId: "qwen-asr", modelId: "qwen3-asr-flash", fallbackAllowed: false },
    });
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(validSampleV2).success).toBe(false);
  });

  it("parses the server-owned formal teacher for every subject and rejects sample Serena for formal math", () => {
    for (const subject of ["chinese", "math", "english"] as const) {
      const parsed = openMaicFormalRuntimeLaunchSchema.parse(formalLaunch(subject));
      if (!("teachingBrief" in parsed.features.generationContract)) {
        throw new Error("expected the formal runtime contract");
      }
      if (!("formalRuntimeContract" in parsed.features)) {
        throw new Error("expected formal classroom evidence");
      }
      expect(parsed.features.generationContract.teachingBrief.course).toMatchObject({
        gradeCode: "primary_3",
        subject,
      });
      expect(parsed.features.generationContract).toMatchObject({
        buildItemId: `formal-${subject}-item`,
        targetFingerprint: "a".repeat(64),
        runtimeRequestId: `formal-${subject}-runtime-request`,
        sourceCourseContentSha256: "8".repeat(64),
        teachingBriefSha256: "9".repeat(64),
        requiredClassroom: formalRuntimeClassroomContract,
        coursewareAuthority: {
          generationOwner: "openmaic",
          providerInvocation: "courseware_generation_only",
          classroomCompilation: "deterministic_no_llm",
          backendProviderCredentialsAccepted: false,
        },
        generation: {
          mode: "deterministic_no_llm",
          enableTTS: false,
          providerCalls: 0,
          automaticRetries: 0,
          maximumAttempts: 1,
        },
      });
      expect(parsed.features.formalRuntimeContract).toEqual(formalRuntimeClassroomContract);
      expect(parsed.features.teacherIdentity).toMatchObject({
        subject,
        avatarPath: formalTeacherIdentities[subject].profileAvatar,
        runtimeAvatar: formalTeacherIdentities[subject].runtimeAvatar,
        teacherProfile: {
          id: formalTeacherIdentities[subject].profileId,
          contentHash: formalTeacherIdentities[subject].profileHash,
        },
        teacherGender: formalTeacherIdentities[subject].teacherGender,
        voiceGender: formalTeacherIdentities[subject].voiceGender,
        voiceId: formalTeacherIdentities[subject].voiceId,
        languageCode: formalTeacherIdentities[subject].languageCode,
      });
    }

    const formalMath = formalLaunch("math");
    formalMath.features.teacherIdentity.voiceId = "Serena";
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(formalMath).success).toBe(false);

    const wrongMathAvatar = formalLaunch("math");
    wrongMathAvatar.features.teacherIdentity.runtimeAvatar = "/avatars/teacher-2.png";
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(wrongMathAvatar).success).toBe(false);

    const mismatchedTeacherEvidence = formalLaunch("math");
    mismatchedTeacherEvidence.features.formalEvidence.teacher.agentId = "another-teacher";
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(mismatchedTeacherEvidence).success).toBe(false);

    const providerBackedGeneration = formalLaunch("math");
    providerBackedGeneration.features.generationContract.generation.providerCalls = 1;
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(providerBackedGeneration).success).toBe(false);

    const staleAttemptContract = formalLaunch("math");
    staleAttemptContract.features.generationContract.generation.maximumAttempts = 3;
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(staleAttemptContract).success).toBe(false);

    const mismatchedRuntimeQuestions = formalLaunch("math");
    mismatchedRuntimeQuestions.features.formalEvidence.runtimeEventAuthority.scenes[5].questionIds = ["q1"];
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(mismatchedRuntimeQuestions).success).toBe(false);
  });

  it("accepts adaptive professional classrooms and derives capability gates from actual scenes", () => {
    for (const subject of ["chinese", "math", "english"] as const) {
      const parsed = openMaicFormalRuntimeLaunchSchema.parse(adaptiveFormalLaunch(subject));
      expect(parsed.features.sceneCount).toBe(12);
      expect(parsed.features.required).toEqual([
        "slides",
        "quiz",
        "multi_agent_roundtable",
        "teacher_actions",
        "diagram",
        "html_game",
        "pbl",
      ]);
      expect(parsed.features.required).not.toContain("simulation");
      expect(parsed.features.required).not.toContain("3d_visualization");
      expect(parsed.features.generationContract).toMatchObject({
        schemaVersion: "mira.openmaic.formal-runtime.v4-deepseek-professional",
        coursewareAuthority: {
          schemaVersion: "mira.openmaic.courseware-authority.v2-professional",
          providerInvocation: "professional_agent",
          classroomCompilation: "professional_skill_workflow",
        },
        professionalCreationPolicy: {
          userPromptRequired: false,
          webSearch: { enabled: true, citationsRequired: true },
        },
        generation: {
          mode: "professional_skill",
          enableWebSearch: true,
          webSearchRequired: true,
          providerInvocation: "openmaic_agent_managed",
        },
      });
      if (!("formalEvidence" in parsed.features)) {
        throw new Error("expected adaptive formal classroom evidence");
      }
      expect(parsed.features.formalEvidence).toMatchObject({
        sceneDistribution: { slide: 5, quiz: 2, interactive: 4, pbl: 1 },
        speechSceneCount: 12,
        speechActionCount: 30,
        widgetTypes: ["diagram", "game"],
        professionalCreation: { verified: true, webSearchEnabled: true },
        research: { verified: true, searchCount: 1, citedSceneCount: 1 },
      });
    }
  });

  it("rejects adaptive manifests whose dynamic count, evidence, research or feature derivation diverges", () => {
    const validAdaptive = adaptiveFormalLaunch("math");

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: { ...validAdaptive.features, sceneCount: 10 },
    }).success).toBe(false);

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: {
        ...validAdaptive.features,
        required: [...validAdaptive.features.required, "simulation"],
      },
    }).success).toBe(false);

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: {
        ...validAdaptive.features,
        evidence: {
          ...validAdaptive.features.evidence,
          diagram: { verified: false, signals: [], reasons: ["not_verified"] },
        },
      },
    }).success).toBe(false);

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: {
        ...validAdaptive.features,
        formalEvidence: {
          ...validAdaptive.features.formalEvidence,
          widgetTypes: ["game", "diagram"],
        },
      },
    }).success).toBe(false);

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: {
        ...validAdaptive.features,
        formalEvidence: {
          ...validAdaptive.features.formalEvidence,
          speechActionCount: 11,
        },
      },
    }).success).toBe(false);

    const tenSceneSpeechOverflow = adaptiveFormalLaunch("math");
    tenSceneSpeechOverflow.features.sceneCount = 10;
    tenSceneSpeechOverflow.features.sceneTypes = ["slide", "quiz", "interactive", "pbl"];
    tenSceneSpeechOverflow.features.formalEvidence.sceneDistribution = {
      slide: 5,
      quiz: 2,
      interactive: 2,
      pbl: 1,
    };
    tenSceneSpeechOverflow.features.formalEvidence.speechSceneCount = 10;
    tenSceneSpeechOverflow.features.formalEvidence.speechActionCount = 201;
    tenSceneSpeechOverflow.features.formalEvidence.runtimeEventAuthority.scenes =
      tenSceneSpeechOverflow.features.formalEvidence.runtimeEventAuthority.scenes.slice(0, 10);
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(tenSceneSpeechOverflow).success).toBe(false);

    const mismatchedRuntimeQuestions = adaptiveFormalLaunch("math");
    mismatchedRuntimeQuestions.features.formalEvidence.runtimeEventAuthority.scenes[5].questionIds = ["q1"];
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(mismatchedRuntimeQuestions).success).toBe(false);

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: {
        ...validAdaptive.features,
        generationContract: {
          ...validAdaptive.features.generationContract,
          generation: {
            ...validAdaptive.features.generationContract.generation,
            enableWebSearch: false,
          },
        },
      },
    }).success).toBe(false);

    expect(openMaicFormalRuntimeLaunchSchema.safeParse({
      ...validAdaptive,
      features: {
        ...validAdaptive.features,
        research: {
          ...validAdaptive.features.research,
          citations: [{
            url: "https://example.edu/primary-curriculum",
            sceneIds: ["unknown-scene"],
          }],
        },
      },
    }).success).toBe(false);
  });

  it("rejects missing, substituted or fallback speech identity on the stage-2 sample", () => {
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: { ...validSampleV2.features, speechAudio: undefined },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: { ...validSampleV2.features, sceneNarration: undefined },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: { ...validSampleV2.features, conversation: undefined },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        speechAudio: { ...sampleSpeechAudioFixture, modelId: "browser-speech" },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        sceneNarration: { ...sampleSceneNarrationFixture, transcriptSceneCount: 9 },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        conversation: {
          ...sampleConversationFixture,
          asr: { ...sampleConversationFixture.asr, providerId: "browser-native" },
        },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        speechAudio: { ...sampleSpeechAudioFixture, verifiedAssetCount: 5 },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        speechAudio: { ...sampleSpeechAudioFixture, signals: [] },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        speechAudio: { ...sampleSpeechAudioFixture, fallbackAllowed: true },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        teacherIdentity: {
          ...sampleTeacherIdentityFixture,
          voiceConfig: { ...sampleTeacherIdentityFixture.voiceConfig, voiceId: "Cherry" },
        },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        evidence: {
          ...validSampleV2.features.evidence,
          teacher_actions: { verified: false, signals: [], reasons: ["not_verified"] },
        },
      },
    }).success).toBe(false);
    expect(openMaicRuntimeLaunchSchema.safeParse({
      ...validSampleV2,
      features: {
        ...validSampleV2.features,
        required: ["slides", "quiz", "simulation", "html_game", "3d_visualization", "multi_agent_roundtable"],
      },
    }).success).toBe(false);
  });

  it("rejects provider secrets and unknown runtime capabilities", () => {
    expect(openMaicRuntimeLaunchSchema.safeParse({ ...valid, apiKey: "must-not-reach-browser" }).success).toBe(false);
    expect(openMaicRuntimeManifestSchema.safeParse({
      ...valid.features,
      present: ["arbitrary_remote_code"],
    }).success).toBe(false);
  });

  it("rejects incomplete or widened v2 manifests", () => {
    expect(openMaicRuntimeManifestSchema.safeParse({
      ...validV2.features,
      evidence: undefined,
    }).success).toBe(false);
    expect(openMaicRuntimeManifestSchema.safeParse({
      ...validV2.features,
      platform: { ...validV2.features.platform, providerKey: "must-not-reach-browser" },
    }).success).toBe(false);
    expect(openMaicRuntimeManifestSchema.safeParse({
      ...validV2.features,
      evidence: { ...validV2.features.evidence, arbitrary_remote_code: { verified: true, signals: [], reasons: [] } },
    }).success).toBe(false);
  });
});
