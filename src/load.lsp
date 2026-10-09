;; APPLOAD this file; keep the entire repository on an AutoCAD trusted path.
(vl-load-com)
(defun EL:LoadModules (/ path el-file missing)
  (if (not *EL:Root*)
    (progn
      (setq path (findfile "load.lsp"))
      (if (not path) (setq path (getfiled "请选择本插件 src/load.lsp 以确定根目录" "" "lsp" 0)))
      (if path (setq *EL:Root* (strcat (vl-filename-directory path) "/../")))))
  (if (and *EL:Root* (>= (getvar "LISPSYS") 1))
    (progn
      (foreach el-file '("common" "config" "geometry" "topology" "statistics" "generation" "main" "simple" "fixed" "panel")
        (if (not (findfile (strcat *EL:Root* "src/" el-file ".lsp"))) (setq missing T)))
      (if missing (princ "\n插件文件不完整；检查 *EL:Root* 和 src 目录。")
        (progn
          (foreach el-file '("common" "config" "geometry" "topology" "statistics" "generation" "main" "simple" "fixed" "panel")
            (load (strcat *EL:Root* "src/" el-file ".lsp")))
          (princ "\n已加载：ELSETUP / ELGAPTEST / ELSTAT / ELTEMPLATE / ELGEN。"))))
    (princ "\n需要 AutoCAD 2021+ Windows、LISPSYS=1/2（更改后重启）及完整插件目录。")))
(EL:LoadModules)
(princ)
