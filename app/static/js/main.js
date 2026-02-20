import { bindCommonHandlers } from "./handlers/commonHandlers.js";
import { bindImportHandlers } from "./handlers/importHandlers.js";
import { bindArtHandlers } from "./handlers/artHandlers.js";
import { updateControlAvailability } from "./ui.js";

bindImportHandlers();
bindCommonHandlers();
bindArtHandlers();
updateControlAvailability();
