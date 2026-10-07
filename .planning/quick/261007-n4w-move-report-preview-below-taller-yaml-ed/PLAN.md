# Plan

Per user follow-up, YAML must fill remaining viewport height with no page scrolling. Use flex layout and shared mobile topbar-height token; scroll YAML internally. Move validation into a compact expandable callout beside unsaved status. Put preview in a wide native dialog so full-width report cards have room without reducing editor height. Verify desktop, mobile, short landscape, invalid-YAML callout and persistent isolated browser regression.

Follow-ups: refresh preview on card selection and ignore stale preview responses. Display all schema validation errors during typing, on draft load and after save; saving incomplete drafts remains allowed, publishing remains blocked. Verify empty layout.height and ci.enabled through server regression and live browser save/reload/publish flow.
