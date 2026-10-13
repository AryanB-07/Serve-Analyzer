// The only Node APIs the tests use (the project doesn't install @types/node).
declare const process: { env: Record<string, string | undefined> };
declare module "node:fs/promises" {
  export function readFile(path: string, encoding: "utf8"): Promise<string>;
}
