;; Date: 2026-10-09. Standalone native cursor preview for an existing block.
(defun c:CCKK (/ *error* saved item)
  (defun *error* (message)
    ;; SETVAR is safe in an error handler; do not issue another CAD command.
    (foreach item saved (setvar (car item) (cdr item)))
    (if (and message (not (wcmatch (strcase message) "*CANCEL*,*QUIT*,*EXIT*,*BREAK*")))
      (princ (strcat "\nCCKK 插入失败：" message))
      (princ "\n已取消插入。"))
    (princ))
  (if (not (tblsearch "BLOCK" "fghjftyuk"))
    (princ "\n当前图纸没有图块 fghjftyuk，请先将该图块复制到本图，再运行 CCKK。")
    (progn
      (foreach item '("CMDECHO" "ATTREQ" "DRAGMODE")
        (setq saved (cons (cons item (getvar item)) saved)))
      (setvar "CMDECHO" 0)
      (setvar "ATTREQ" 0)
      (setvar "DRAGMODE" 2)
      (princ "\n移动鼠标预览配电回路图块，左键点击插入，Esc 取消。")
      ;; Preset scale and rotation before PAUSE so only placement is interactive.
      (command "_.-INSERT" "fghjftyuk" "_Scale" 1.0 "_Rotate" 0.0 pause)
      (foreach item saved (setvar (car item) (cdr item)))))
  (princ))
(princ)
