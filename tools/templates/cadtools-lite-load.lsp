;; Date: 2026-10-16. UTF-8 source template; build emits strict GB2312.
;; CADTools sets *EL:CADToolsRoot* to this module's installation directory.
(setq *EL:BootstrapTick* (getvar "MILLISECS"))
(vl-load-com)
(setq *EL:LiteVersion* "@VERSION@" *EL:LiteMarker* "@MARKER@"
  *EL:LiteFiles* '(@FILES@))
(defun EL:LiteNormalize (root)
  (if (and (equal (type root) 'STR) (/= root ""))
    (strcat (vl-string-right-trim "/\\" root) "/")))
(defun EL:LiteRootValid (root / ok relative)
  (if (setq root (EL:LiteNormalize root))
    (progn (setq ok T)
      (foreach relative *EL:LiteFiles*
        (if (not (findfile (strcat root relative))) (setq ok nil))) ok)))
(defun EL:LiteCandidate (path / root)
  (if (and (equal (type path) 'STR) (/= path ""))
    (progn
      (if (and (findfile path) (not (vl-file-directory-p path)))
        (setq path (vl-filename-directory path)))
      (setq root (EL:LiteNormalize path))
      (cond ((EL:LiteRootValid root) root)
        ((and root (EL:LiteRootValid (strcat root "../"))) (strcat root "../"))))))
(defun EL:LiteFindRoot (/ root path)
  ;; An explicit but broken install must fail, never silently load another copy.
  (if *EL:CADToolsRoot*
    (EL:LiteCandidate *EL:CADToolsRoot*)
    (progn
      (setq path (vl-registry-read
        (strcat "HKEY_CURRENT_USER\\" (vlax-product-key)
          "\\Profiles\\" (getvar "CPROFILE") "\\Dialogs\\Appload") "MainDialog")
        root (EL:LiteCandidate path))
      (if (not root) (setq root (EL:LiteCandidate (findfile *EL:LiteMarker*))))
      (if (not root) (setq root (EL:LiteCandidate
        (getenv (strcat "EL_CADTOOLS_" *EL:LiteVersion*))))) root)))
(defun EL:LiteInitData (/ base folder ok)
  (setq *EL:LiteDataRoot* nil)
  (if (setq base (EL:LiteNormalize (getenv "LOCALAPPDATA")))
    (progn
      (setq ok T)
      (foreach folder '("Emergency-Lighting/" "Emergency-Lighting/CADTools/"
                        "Emergency-Lighting/CADTools/config/" "Emergency-Lighting/CADTools/output/")
        (if (not (or (vl-file-directory-p (strcat base folder))
                     (vl-mkdir (strcat base folder)))) (setq ok nil)))
      (if ok (setq *EL:LiteDataRoot* (strcat base "Emergency-Lighting/CADTools/"))))))
(defun EL:LiteRelocate (/ path root)
  (if (setq path (getfiled "选择精简版 src/load.lsp" "" "lsp" 0))
    (if (setq root (EL:LiteCandidate path))
      (progn (setq *EL:CADToolsRoot* root) (EL:LiteLoad))
      (princ "\n所选目录不是当前精简版的完整运行目录，原目录保持不变。"))))
(defun EL:LiteLoadWork (/ root module token)
  (setq root (EL:LiteFindRoot))
  (cond
    ((not root) (setq *EL:StartupError* "精简版运行文件不完整或目录未指定，请检查 CADTools 安装目录。") nil)
    ((not (EL:LiteInitData)) (setq *EL:StartupError* "无法建立当前用户数据目录，请检查 LOCALAPPDATA。") nil)
    (T
      (setq *EL:Root* root)
      (foreach module '(@MODULES@)
        (if (equal module "common")
          (progn (load (strcat root "src/common.lsp"))
            (EL:MonitorLoadBegin *EL:BootstrapTick*))
          (progn
            (setq *EL:MonitorLabel* (strcat module ".lsp") token (EL:PerfBegin "LOAD_MODULE"))
            (load (strcat root "src/" module ".lsp"))
            (EL:PerfEnd token 'returned) (setq *EL:MonitorLabel* nil))))
      (defun c:ELROOT () (EL:LiteRelocate) (princ))
      (EL:ClearPickHighlights)
      (setq *EL:Result* nil *EL:DeviceResult* nil)
      (EL:PerfCall "LOAD_LIBRARY" 'EL:DLDefaultStartup nil)
      (setenv (strcat "EL_CADTOOLS_" *EL:LiteVersion*) root)
      T)))
(defun EL:LiteLoad (/ result)
  (setq *EL:BootstrapTick* (getvar "MILLISECS")
    *EL:Root* nil *EL:LiteDataRoot* nil *EL:MonitorLoadReady* nil
    *EL:StartupAttempted* T *EL:StartupError* nil *EL:PackageMarker* *EL:LiteMarker*)
  (setq result (vl-catch-all-apply 'EL:LiteLoadWork nil))
  (if (vl-catch-all-error-p result)
    (setq *EL:StartupError* (vl-catch-all-error-message result) result nil))
  (setq *EL:MonitorLoadReady* result)
  (if result
    (progn
      (EL:MonitorLoadEnd 'load-finished)
      (princ (strcat "\n已加载（CAD2020 " *EL:LiteVersion* "）。数据目录：" *EL:LiteDataRoot*))
      (EL:StartupCommandHint T))
    (progn
      (vl-catch-all-apply 'EL:MonitorLoadEnd (list 'load-failed))
      (setq *EL:Root* nil)
      (princ (strcat "\n精简版启动未完成：" *EL:StartupError*)))) result)
(EL:LiteLoad)
(princ)
