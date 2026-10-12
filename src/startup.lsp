;; Date: 2026-10-11. Resolve the current package without changing CAD security.
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
(defun EL:StartupEmbeddedRoot () nil)
(defun EL:StartupDecode64 (text / alphabet index digit bits value out)
  ;; Date: 2026-10-12. Decode bounded, four-character-aligned build fragments.
  (setq alphabet "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    index 1 bits 0 value 0)
  (repeat (strlen text)
    (if (/= (substr text index 1) "=")
      (progn
        (setq digit (vl-string-search (substr text index 1) alphabet)
          value (+ (* value 64) digit) bits (+ bits 6))
        (if (>= bits 8)
          (progn
            (setq bits (- bits 8) digit (expt 2 bits)
              out (cons (fix (/ value digit)) out) value (rem value digit))))))
    (setq index (1+ index)))
  (reverse out))
(defun EL:StartupBinaryWork (path chunks / chunk bytes array actual good)
  (if (EL:DLMkdir (vl-filename-directory path))
    (progn
      (setq *EL:StartupStream* (vlax-create-object "ADODB.Stream"))
      (vlax-put-property *EL:StartupStream* 'Type 1)
      ;; Date: 2026-10-12. Visual LISP needs all five ADO optional slots.
      (setq *EL:StartupStage* "STREAM_OPEN")
      (vlax-invoke-method *EL:StartupStream* 'Open nil 0 -1 "" "")
      (setq *EL:StartupStage* "BINARY_WRITE")
      (foreach chunk chunks
        (setq bytes (EL:StartupDecode64 chunk)
          array (vlax-make-safearray 17 (cons 0 (1- (length bytes)))))
        (vlax-safearray-fill array bytes)
        (vlax-invoke-method *EL:StartupStream* 'Write (vlax-make-variant array)))
      ;; Only the versioned runtime seed is replaced, never the user's library.
      (setq *EL:StartupStage* "SAVE_TO_FILE")
      (vlax-invoke-method *EL:StartupStream* 'SaveToFile path 2)
      (setq *EL:StartupStage* "BINARY_READBACK")
      (vlax-invoke-method *EL:StartupStream* 'LoadFromFile path)
      (setq good T)
      (foreach chunk chunks
        (setq bytes (EL:StartupDecode64 chunk)
          actual (vlax-invoke-method *EL:StartupStream* 'Read (length bytes)))
        (if (equal (type actual) 'VARIANT) (setq actual (vlax-variant-value actual)))
        (if (not (equal bytes (vlax-safearray->list actual))) (setq good nil)))
      good)))
(defun EL:StartupWriteBase64 (path chunks / result *EL:StartupStream* *EL:StartupStage*)
  (setq *EL:StartupStage* "STREAM_CREATE")
  (setq result (vl-catch-all-apply 'EL:StartupBinaryWork (list path chunks)))
  (if *EL:StartupStream* (vl-catch-all-apply 'vlax-invoke-method (list *EL:StartupStream* 'Close)))
  (if *EL:StartupStream* (vl-catch-all-apply 'vlax-release-object (list *EL:StartupStream*)))
  (if (vl-catch-all-error-p result)
    (setq *EL:StartupError* (strcat path " [" *EL:StartupStage* "] : " (vl-catch-all-error-message result))))
  (and (not (vl-catch-all-error-p result)) result))
(defun EL:StartupResource (writer path data / result)
  (setq result (vl-catch-all-apply writer (list path data)))
  (if (or (vl-catch-all-error-p result) (not result))
    (progn
      (if (not *EL:StartupError*)
        (setq *EL:StartupError* (strcat path " : "
          (if (vl-catch-all-error-p result) (vl-catch-all-error-message result) "文件写入或回读校验失败"))))
      nil)
    T))
(defun EL:StartupSelectRoot (marker / path)
  ;; Date: 2026-10-10. A confirmed package path keeps diagnostics beside the ZIP.
  (princ "\n请选择解压包内的 START-CAD2020.lsp；日志将保存在该包的 output 文件夹。")
  (if (setq path (getfiled "确认应急照明交付目录" "START-CAD2020.lsp" "lsp" 0))
    (EL:StartupCandidate path marker)))
(defun EL:StartupRememberRoot (root marker)
  (if root (vl-catch-all-apply 'setenv (list (strcat "EL_PACKAGE_ROOT_" marker) root)))
  root)
(defun c:ELROOT (/ root)
  (if (and *EL:PackageMarker* (setq root (EL:StartupSelectRoot *EL:PackageMarker*)))
    (progn
      (setq *EL:Root* (EL:StartupRememberRoot root *EL:PackageMarker*))
      (princ (strcat "\n插件数据目录已设置：" root "；后续日志保存在 output 文件夹。")))
    (princ "\n未选择当前版本的完整交付目录，原目录保持不变。"))
  (princ))
(defun EL:StartupWriteLines (path lines / stream result line)
  (if (setq stream (open path "w"))
    (progn
      (setq result (vl-catch-all-apply
        '(lambda () (foreach line lines (write-line line stream))) nil))
      (close stream)
      (if (not (vl-catch-all-error-p result))
        (progn
          (setq stream (open path "r") result T)
          (if stream
            (progn
              (foreach line lines
                (if (not (equal line (read-line stream))) (setq result nil)))
              (if (read-line stream) (setq result nil))
              (close stream) result)))))))
(defun EL:StartupRoot (marker / directory root path filename)
  (setq *EL:StartupError* nil)
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
  (if (not root)
    (setq root (EL:StartupCandidate (getenv (strcat "EL_PACKAGE_ROOT_" marker)) marker)))
  ;; Never prompt during startup. Manual relocation belongs to c:ELROOT only.
  (if root (EL:StartupRememberRoot root marker))
  (if (not root)
    (progn
      (setq root (vl-catch-all-apply 'EL:StartupEmbeddedRoot nil))
      (if (vl-catch-all-error-p root)
        (setq *EL:StartupError* (vl-catch-all-error-message root) root nil))
      (if root (princ "\n未确认交付目录，暂用本地运行目录；输入 ELROOT 可改回交付包目录。"))))
  (setq *EL:Root* root *EL:PackageMarker* marker)
  (if root (princ (strcat "\n插件数据目录：" root))
    (princ (strcat "\n自动初始化失败："
      (cond (*EL:StartupError*) (T "无法建立完整本地运行目录，请检查 LOCALAPPDATA 路径。")))))
  root)
