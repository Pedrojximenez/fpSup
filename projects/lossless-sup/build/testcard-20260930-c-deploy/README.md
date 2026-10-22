testcard-20260930-c with fpSup.BIN zero-padded to the loader read cap (61440 B) so the
card file (61,440 B from the previous r5 build; putfile cannot truncate) is fully
overwritten and deploy.py can read it back whole. Same sections, entry and body length.
