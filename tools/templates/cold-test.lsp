;; Date: 2026-10-22. APPLOAD only registers. The command owns the full read-only probe payload.
(defun @COMMAND@:Initialize ()
@STARTUP@
)
(defun c:@COMMAND@ (/ outcome)
  (setq *EL:MonitorLoadReady* nil)
  (setq outcome (vl-catch-all-apply '@COMMAND@:Initialize nil))
  (cond
    ((vl-catch-all-error-p outcome)
      (princ (strcat "\n@COMMAND@ 初始化失败：" (vl-catch-all-error-message outcome))))
    ((and *EL:MonitorLoadReady* (equal *EL:PackageMarker* "@MARKER@") *EL:Root*)
      ;; Initializer installs src/cold-probe.lsp's command before dispatch.
      (c:@COMMAND@))
    (T (princ "\n@COMMAND@ 未完成初始化，请查看上方具体错误。")))
  (princ))
(princ "\n只读 .NET 冷路径原型 v@VERSION@ 已注册：输入 @COMMAND@ 开始。")
(princ)
