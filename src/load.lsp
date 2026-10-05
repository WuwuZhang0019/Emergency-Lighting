;; APPLOAD this file; keep the entire repository on an AutoCAD trusted path.
(vl-load-com)
(if (not *EL:Root*)
  (setq *EL:Root* (strcat (vl-filename-directory (findfile "load.lsp")) "/../")))
(foreach el-file '("common" "config" "geometry" "topology" "statistics" "generation" "main")
  (if (findfile (strcat *EL:Root* "src/" el-file ".lsp"))
    (load (strcat *EL:Root* "src/" el-file ".lsp"))))
(princ "\n应急照明插件已加载。ELSETUP 采样；ELSAMPLE 追加角色。")
(princ)
