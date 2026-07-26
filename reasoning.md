# S.Q.U.I.N.T. Architectural Decisions & Code Review Notes

During our recent external code review, a third-party audit returned 28 optimization recommendations for the S.Q.U.I.N.T. codebase. We have evaluated these suggestions carefully to balance robust application design with our principle of keeping the codebase lean and free of over-engineering (YAGNI).

Below is the breakdown of the decisions we made regarding these suggestions.

---

## ✅ Accepted & Implemented (Lean Fixes)

We integrated the following suggestions because they solved legitimate edge cases and improved accuracy without unnecessarily bloating the codebase:

1. **Queue Mutation Locks (`#1`)**: 
   We implemented strict UI state locking during active processing. The Add, Remove, and Clear buttons are now disabled when a batch is running to prevent indexing crashes and race conditions if a user tries to delete a video that is actively being processed.
2. **Worker Exception Halting (`#2`)**: 
   Added an explicit `break` inside the worker's exception handler. Previously, if the FFmpeg engine crashed on a video, the worker would blindly attempt to start the next video in a broken state. Now, it halts cleanly.
3. **Relative Path Output Structure (`#5`)**: 
   Fixed a bug in `os.path.relpath(os.path.dirname(path), base_folder)` that caused nested folder structures (e.g., `Season 2/Episode 1`) to be improperly flattened when mapping to the output directory.
4. **Accurate Frame-Based Progress (`#8`)**: 
   The master queue progress calculation was updated to use `(completed_frames + current_frames) / total_batch_frames` rather than just equally weighting short clips alongside 2-hour movies.
5. **Lazy Directory Creation (`#9`)**: 
   Moved `os.makedirs` from the UI to the engine so directories are only created at the exact moment FFmpeg begins writing to them, preventing ghost folders if a user cancels a queue early.
6. **Code & UI Cleanups (`#18-22, #29`)**: 
   Removed unused imports, fixed `statusBar` shadowing, eliminated duplicated drag-and-drop definitions, and ensured the UI properly clears red error stylesheets if a failed item is restarted.

---

## ❌ Rejected (Over-Engineering / YAGNI)

We explicitly rejected the following suggestions as they violate our principle of lean software design. Our goal is to maintain a highly readable, tightly integrated 3-file architecture.

1. **Massive Structural Refactoring (`#725`)**:
   The reviewer suggested splitting our 3 simple modules into a 15+ file enterprise layout (`ui/`, `workers/`, `services/`, `models/`) with explicit dataclasses for every setting. We rejected this outright. The current monolithic but logically partitioned layout is significantly easier to maintain and distribute.
2. **Atomic Job Saves & Versioned Schemas (`#13-17`)**:
   The reviewer suggested writing `.vuj` files to a `.tmp` file first, swapping atomic pointers, and adding schema tracking and validation logic. Our JSON-based job tracker is simple, effective, and inherently safe due to Qt's robust event loop. The added complexity is unwarranted.
3. **QMessageBox on Shutdown (`#3`)**:
   The reviewer suggested showing a warning dialog if the user attempts to close the app while it's processing. We had already implemented a superior solution: silent background `.vuj` state autosaving. Annoying the user with prompts is a step backward in UX.
4. **VRAM Auto-Tiling Prediction (`#27`)**:
   Predicting exact CUDA memory usage dynamically based on resolution, FP16 state, and arbitrary model architectures is a nightmare to maintain. We decided to keep the "Tile Size" dropdown fully manual, allowing the user to explicitly handle OOM constraints.
5. **Background Probing Thread (`#6`)**:
   Threading `ffprobe` operations when adding files to the queue was deemed unnecessary, as `ffprobe` evaluates headers in ~30ms. The synchronous UI block is imperceptible under normal use cases.
6. **Defensive Path Collision (`#10-12`)**:
   The reviewer recommended writing 50+ lines of logic to prevent a user from selecting the same output file twice. Since FFmpeg cleanly overwrites files anyway, we deemed this unnecessary hand-holding.
