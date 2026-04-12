import fs from 'node:fs'
import path from 'node:path'

const filePath = path.resolve(process.cwd(), 'src/types/api.gen.ts')
const source = fs.readFileSync(filePath, 'utf8')

const aliasBlock = String.raw`

export type ProjectListItem = Omit<components["schemas"]["ProjectListItem"], "status"> & { status?: string };
export type ProjectInitRequest = Pick<components["schemas"]["ProjectInitRequest"], "project_id"> & Partial<Omit<components["schemas"]["ProjectInitRequest"], "project_id">>;
export type ProjectInitResponse = components["schemas"]["ProjectInitResponse"];
export type ProjectStatusResponse = components["schemas"]["ProjectStatusResponse"];
export type MetricsHistoryItem = components["schemas"]["MetricsHistoryItem"];
export type CostSummaryResponse = components["schemas"]["CostSummaryResponse"];
export type CostHistoryItem = components["schemas"]["CostHistoryItem"];
export type ProjectSettingsResponse = components["schemas"]["ProjectSettingsResponse"];
export type RunChapterRequest = components["schemas"]["RunChapterRequest"];
export type RunChapterResponse = components["schemas"]["RunChapterResponse"];
export type PlanChapterRequest = components["schemas"]["PlanChapterRequest"];
export type PlanChapterResponse = components["schemas"]["PlanChapterResponse"];
export type MetricsRequest = components["schemas"]["MetricsRequest"];
export type MetricsResponse = components["schemas"]["MetricsResponse"];
export type CheckChapterResponse = Omit<components["schemas"]["CheckChapterResponse"], "issues"> & { issues: ConsistencyIssue[] };
export type HumanizeResponse = components["schemas"]["HumanizeResponse"];
export type CostResponse = components["schemas"]["CostResponse"];
export type ChapterListItem = components["schemas"]["ChapterListItem"];
export type ChapterTextResponse = components["schemas"]["ChapterTextResponse"];
export type ExportNovelResponse = components["schemas"]["ExportNovelResponse"];
export type PlotNode = components["schemas"]["PlotNode"];
export type PlotEdge = components["schemas"]["PlotEdge"];
export type PlotGraphData = components["schemas"]["PlotGraphData"];
export type DialogueExample = { context: string; dialogue: string; action?: string };
export type Motivation = { desire: string; fear?: string; tension: number; notes?: string };
export type VoiceFingerprint = Partial<components["schemas"]["VoiceFingerprint"]> & { default_length?: "short" | "medium" | "long" };
export type BehaviorConstraintDetail = components["schemas"]["BehaviorConstraint"];
export type CharacterSummary = components["schemas"]["CharacterSummary"];
export type CharacterDetail = Omit<components["schemas"]["CharacterState"], "behavior_constraints" | "dialogue_examples" | "motivations" | "voice_fingerprint"> & {
  behavior_constraints: BehaviorConstraintDetail[];
  dialogue_examples: DialogueExample[];
  motivations: Motivation[];
  voice_fingerprint?: {
    under_pressure: string;
    when_lying: string;
    deflection: string;
    emotional_peak: string;
    default_length: string;
  };
};
export type CharacterDrive = components["schemas"]["CharacterDrive"];
export type RelationshipProfile = components["schemas"]["RelationshipProfile"];
export type CharacterRuntime = components["schemas"]["CharacterRuntime"];
export type MemoryRecord = Omit<components["schemas"]["MemoryRecord"], "metadata" | "similarity"> & {
  similarity?: number;
  metadata: Record<string, unknown>;
};
export type MemorySnapshot = Omit<components["schemas"]["MemorySnapshot"], "recent_anchors"> & { recent_anchors: MemoryRecord[] };
export type MemorySearchResult = Omit<components["schemas"]["MemorySearchResult"], "results"> & { results: MemoryRecord[] };
export type LLMProviderStatus = components["schemas"]["LLMProviderStatus"];
export type LLMCurrentConfig = components["schemas"]["LLMCurrentConfig"];
export type LLMSettingsResponse = components["schemas"]["LLMSettingsResponse"];
export type LLMTestResult = components["schemas"]["LLMTestResult"];
export type LLMProviderConfig = components["schemas"]["LLMProviderUpdateRequest"];
export type LLMProviderName = "openai" | "anthropic" | "ollama" | "deepseek" | "custom";
export type CreateSessionRequest = Partial<components["schemas"]["CreateSessionRequest"]>;
export type CreateSessionResponse = components["schemas"]["CreateSessionResponse"];
export type StepSessionRequest = components["schemas"]["SessionStepRequest"];
export type TurnRecordResponse = components["schemas"]["TurnRecordResponse"];
export type InterruptRequest = components["schemas"]["InterruptRequest"];
export type RollbackRequest = components["schemas"]["RollbackRequest"];
export type SessionStatusResponse = components["schemas"]["SessionStatusResponse"];
export type SessionSummary = Omit<components["schemas"]["SessionSummary"], "key_decisions" | "character_delta"> & {
  word_count?: number;
  key_decisions: Array<{ turn?: number; choice?: string }>;
  character_delta: Array<{ name?: string; change?: string }>;
};
export type TurnRecord = TurnRecordResponse & {
  decision_type?: string
  risk_levels?: string[]
  rolled_back?: boolean
  is_rewrite?: boolean
  rewrite_index?: number
};
export type ConceptData = components["schemas"]["ConceptData"];
export type RegionGeography = components["schemas"]["RegionGeography"];
export type RegionRace = components["schemas"]["RegionRace"];
export type RegionCivilization = components["schemas"]["RegionCivilization"];
export type RegionPowerAccess = components["schemas"]["RegionPowerAccess"];
export type Region = components["schemas"]["Region"];
export type Faction = components["schemas"]["Faction"];
export type PowerLevel = components["schemas"]["narrative_os__core__world_sandbox__PowerLevel"];
export type PowerSystem = components["schemas"]["narrative_os__core__world_sandbox__PowerSystem-Output"];
export type WorldRelation = components["schemas"]["WorldRelation"];
export type TimelineSandboxEvent = components["schemas"]["TimelineSandboxEvent"];
export type WorldSandboxData = components["schemas"]["WorldSandboxData"];
export type WorldState = components["schemas"]["WorldState"];
export type PowerTemplateSummary = components["schemas"]["PowerTemplateSummary"];
export type WorldbuilderStartResponse = components["schemas"]["WorldbuilderStartResponse"];
export type WorldbuilderStepResponse = components["schemas"]["WorldbuilderStepResponse"];
export type PluginInfo = components["schemas"]["PluginInfo"];
export type StylePreset = components["schemas"]["StylePreset"];
export type ConsistencyIssue = components["schemas"]["ConsistencyIssue"];
export type ConsistencyReport = components["schemas"]["ConsistencyReport"];
export type DeleteCharacterResponse = components["schemas"]["DeleteCharacterResponse"];
export type VoiceTestResponse = components["schemas"]["TestVoiceResponse"];
export type SavePoint = components["schemas"]["SavePoint"];
export type ControlModeResponse = components["schemas"]["ControlModeResponse"];
export type AgendaResponse = components["schemas"]["AgendaResponse"];
export type SessionCommitResponse = components["schemas"]["SessionCommitResponse"];
export type FinalizeWorldResponse = components["schemas"]["FinalizeWorldResponse"];
export type AISuggestRelationsResponse = components["schemas"]["AISuggestRelationsResponse"];
export type AIExpandResponse = components["schemas"]["AIExpandResponse"];
export type AIImportTextResponse = components["schemas"]["AIImportTextResponse"];
export type AIConsistencyResponse = components["schemas"]["AIConsistencyResponse"];
export type WorldOverviewResponse = components["schemas"]["WorldOverviewResponse"];
export type WorldMapLayoutResponse = components["schemas"]["WorldMapLayoutResponse"];
`

if (!source.includes('export type ProjectListItem = components["schemas"]["ProjectListItem"]')) {
  fs.writeFileSync(filePath, source + aliasBlock, 'utf8')
}