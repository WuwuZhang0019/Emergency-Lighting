;; Date: 2026-10-20. Full standalone entry; registration never opens or edits a drawing.
;; No dependency on LOAD preserving a source pathname, APPLOAD history or ACAD paths.
(defun @COMMAND@:Initialize ()
  (setq *EL:LiteVersion* nil)
@STARTUP@
)
(defun c:@COMMAND@ (/ outcome)
  (setq *EL:MonitorLoadReady* nil)
  (setq outcome (vl-catch-all-apply '@COMMAND@:Initialize nil))
  (cond
    ((vl-catch-all-error-p outcome)
      (princ (strcat "\n@COMMAND@ 初始化失败：" (vl-catch-all-error-message outcome))))
    ((and *EL:MonitorLoadReady* (equal *EL:PackageMarker* "@MARKER@")
        *EL:Root* C:ELSTAT)
      (princ "\n@COMMAND@ 使用完整版 v@VERSION@；正在打开应急照明面板。")
      (c:ELSTAT))
    (T (princ "\n@COMMAND@ 未完成初始化，请查看上方具体错误；本次未运行统计。")))
  (princ))
(princ "\n完整版 v@VERSION@ 已注册：输入 @COMMAND@ 开始。")
(princ)
