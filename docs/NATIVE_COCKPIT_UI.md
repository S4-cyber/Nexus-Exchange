# Native cockpit interface

Owner-requested UI quality-of-life changes. Base: PR #77 head
6f1cfadaf66eb5ebeae21879f5964ee4b4c4cab0, both Python and Windows CI
passed. The independent PR #76 packaging branch is preserved unchanged.

- Shared clam ttk theme and Tk option defaults: near-black, neon green,
  pale readable green text, purple focus/selection and angular border trim.
  Covers main dashboard, all eight native workspace types and child windows
  built by desktop.py. Native OS file dialogs, message boxes and title bars
  may retain operating-system styling.
- Reserved bottom-right help area in every decorated window. Exact
  plain-language help for known actions, bounded generic help for other
  controls. Hover and keyboard focus use each toplevel's existing bindtags.
  No button command, confirmation, permission, worker or halt changes.
  Emergency halt retains its existing command and is visually distinguished.
- Exposed top and side starfield rails remain visible around content rather
  than being hidden behind opaque Tk widgets. Angular layered green/purple
  trim, bounded moving stars, shared Animate stars toggle. No flashing,
  network, assets, external package or hidden rendering process. Hidden or
  paused windows do not advance stars; destruction cancels the timer.
  Native windows retain layout managers; geometry is screen-bounded,
  and crowded main buttons are separated into rows. The app's ordinary
  workspace remains fully opaque and legible.
- Seven pure regression tests and actual Tk theme/help/animation/cleanup
  checks in existing source and frozen Windows GUI smoke. No local GUI
  visual inspection claimed. Confirm appearance and layout manually on
  representative monitor sizes before release.
