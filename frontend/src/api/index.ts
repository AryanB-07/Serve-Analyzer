import { httpClient, type ApiClient } from "./client";
import { createMockClient } from "./mockClient";

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

export const api: ApiClient = USE_MOCKS ? createMockClient() : httpClient;

export { ApiError, UploadAbortedError } from "./client";
export type { ApiClient } from "./client";
