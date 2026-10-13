import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// findBy*/waitFor give up after 1 s by default. On a busy CI runner (two cores, several test
// files at once) a page can take longer than that to settle, so allow more; passing tests are
// no slower, since these return as soon as the element appears.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => cleanup());
