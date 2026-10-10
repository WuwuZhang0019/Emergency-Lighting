;; Date: 2026-10-10. Resolve the current package without changing CAD security.
(defun EL:StartupCandidate (directory marker / root)
  ;; MainDialog may contain the selected filename, not only its directory.
  (if (and (equal (type directory) 'STR) (findfile directory)
           (not (vl-file-directory-p directory)))
    (setq directory (vl-filename-directory directory)))
  (if (setq root (EL:NormalizeRoot directory))
    (cond
      ((and (findfile (strcat root marker)) (EL:RootValid root)) root)
      ((and (findfile (strcat root "../" marker)) (EL:RootValid (strcat root "../")))
        (EL:NormalizeRoot (strcat root "../"))))))
(defun EL:StartupRegistryDirectory ()
  (vl-registry-read
    (strcat "HKEY_CURRENT_USER\\" (vlax-product-key)
      "\\Profiles\\" (getvar "CPROFILE") "\\Dialogs\\Appload") "MainDialog"))
(defun EL:StartupRoot (marker / directory root path filename)
  ;; APPLOAD's last folder is only a candidate: require this version's marker
  ;; and the complete package before using it. No stale-root fallback.
  (setq directory (vl-catch-all-apply 'EL:StartupRegistryDirectory nil))
  (if (not (vl-catch-all-error-p directory))
    (setq root (EL:StartupCandidate directory marker)))
  (if (and (not root) (setq path (findfile marker)))
    (setq root (EL:StartupCandidate (vl-filename-directory path) marker)))
  ;; A support path can point at src, where the package marker is not visible.
  (foreach filename '("START-CAD2020.lsp" "load.lsp")
    (if (and (not root) (setq path (findfile filename)))
      (setq root (EL:StartupCandidate path marker))))
  (setq *EL:Root* root)
  (EL:EnsureRoot))
