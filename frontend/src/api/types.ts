import type { components } from "./schema";

type Schemas = components["schemas"];

export type AnalysisSummary = Schemas["AnalysisSummary"];
export type AnalysisStatus = AnalysisSummary["status"];
export type AnalysisList = Schemas["AnalysisList"];
export type AnalysisResult = Schemas["AnalysisResult"];
export type CreateAnalysisRequest = Schemas["CreateAnalysisRequest"];
export type CreateAnalysisResponse = Schemas["CreateAnalysisResponse"];
export type UploadTarget = Schemas["UploadTarget"];
export type FramesPayload = Schemas["FramesPayload"];
export type PhaseFrames = Schemas["PhaseFrames"];
export type FeedbackItem = Schemas["FeedbackItem"];
export type MetricRange = Schemas["MetricRange"];
export type ErrorCode = Schemas["ApiError"]["code"];
export type Hand = AnalysisSummary["hand"];

export type PhaseName = keyof Schemas["PhaseMetrics"];
export type MetricName = keyof Schemas["MetricValues"];
export type MetricStatus = NonNullable<Schemas["MetricLabels"][MetricName]>;
export type LandmarkName = keyof Schemas["RawLandmarks"];
