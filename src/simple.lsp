;; Date: 2026-10-13. Explicit circuit starts are one-way search boundaries.
(defun EL:CircuitStartsValid (rows / good seen row)
  (setq good (listp rows))
  (foreach row rows
    (if (not (and (EL:OnlyKeys row '(wire end point))
        (equal (type (EL:Get 'wire row)) 'STR) (/= (EL:Get 'wire row) "")
        (not (member (EL:Get 'wire row) seen)) (member (EL:Get 'end row) '(start end))
        (listp (EL:Get 'point row)) (= (length (EL:Get 'point row)) 3)
        (vl-every 'numberp (EL:Get 'point row)))) (setq good nil))
    (setq seen (cons (EL:Get 'wire row) seen))) good)
(defun EL:StartBoundaryPoint (point snapshot cfg)
  (vl-some '(lambda (row) (and
    (<= (EL:Norm (EL:V- point (EL:Get 'point row))) (EL:Get 'eps_touch (EL:Get 'params cfg)))
    (<= (abs (- (caddr point) (caddr (EL:Get 'point row)))) (EL:GapEpsilon))))
    (EL:Get 'circuit-starts snapshot)))
(defun EL:StartBoundaryBounds (wire tolerance / bounds lo hi margin)
  ;; Date: 2026-10-21. Fresh contact bounds enclose all source segments/strips.
  ;; Missing or unprovable envelopes retain the exact contact path. Roundoff
  ;; expands this broad phase only; the final EL:Touches tolerances stay intact.
  (setq bounds (EL:Get 'contact-bounds wire))
  (if (and (listp bounds) (equal (vl-list-length bounds) 2)
      (listp (setq lo (car bounds))) (equal (vl-list-length lo) 3)
      (listp (setq hi (cadr bounds))) (equal (vl-list-length hi) 3)
      (vl-every 'EL:Number lo) (vl-every 'EL:Number hi)
      (<= (car lo) (car hi)) (<= (cadr lo) (cadr hi)) (<= (caddr lo) (caddr hi))
      (EL:NonNegative tolerance))
    (progn
      (setq margin (EL:ContactQueryRoundoff bounds nil))
      (list (list (- (car lo) tolerance margin) (- (cadr lo) tolerance margin)
                  (- (caddr lo) (EL:GapEpsilon) margin))
            (list (+ (car hi) tolerance margin) (+ (cadr hi) tolerance margin)
                  (+ (caddr hi) (EL:GapEpsilon) margin))))))
(defun EL:StartSnapshot (snapshot cfg panel / starts row wire ep ids kept removed ends perf batch result
    bounds point pairs rejected exact fallback removed-ids)
  ;; Date: 2026-10-21. Keep source order and exact contact; skip only distant pairs.
  (setq perf (EL:PerfBegin "START_SNAPSHOT") starts (EL:Get 'circuit-starts cfg))
  (EL:Require (and starts (EL:CircuitStartsValid starts)) "回路起始端记录无效，请重新拾取。")
  (foreach row starts
    (setq wire (EL:By 'id (EL:Get 'wire row) (EL:Get 'wires snapshot))
      ep (EL:By 'key (list (EL:Get 'wire row) (EL:Get 'end row)) (EL:Get 'ends wire)))
    (EL:Require (and wire ep (not (EL:Get 'issues wire))
      (equal (EL:Get 'point row) (EL:Get 'point ep) (EL:GapEpsilon)))
      "已选回路起始导线缺失、改变图层或起点已移动，请重新拾取。")
    (setq ids (cons (EL:Get 'wire row) ids)))
  ;; Retain excluded source geometry in the snapshot for exact freshness checks.
  ;; A common trunk/feeder touching a picked root must never become a path back.
  (setq batch (EL:PerfBegin "START_BOUNDARY_FILTER") pairs 0 rejected 0 exact 0 fallback 0)
  (foreach wire (EL:Get 'wires snapshot)
    (if (and (not (member (EL:Get 'id wire) ids))
        (progn
          (setq bounds (EL:StartBoundaryBounds wire (EL:Get 'eps_touch (EL:Get 'params cfg))))
          (if (not bounds) (setq fallback (1+ fallback)))
          (vl-some '(lambda (row)
            (setq pairs (1+ pairs) point (EL:Get 'point row))
            (if (or (not bounds) (EL:InBounds point bounds 0.0))
              (progn (setq exact (1+ exact))
                (EL:Touches point (EL:Get 'segments wire)
                  (EL:Get 'eps_touch (EL:Get 'params cfg)) (EL:GapEpsilon)))
              (progn (setq rejected (1+ rejected)) nil))) starts)))
      (setq removed (cons wire removed)) (setq kept (cons wire kept))))
  (setq kept (reverse kept))
  (EL:PerfEnd batch 'returned)
  (EL:PerfCount "start-boundary-pair-checks" pairs)
  (EL:PerfCount "start-boundary-bounds-rejected" rejected)
  (EL:PerfCount "start-boundary-exact-checks" exact)
  (EL:PerfCount "start-boundary-bounds-fallback-wires" fallback)
  (setq batch (EL:PerfBegin "START_ENDS_BUILD"))
  (foreach wire kept
    (foreach ep (EL:Get 'ends wire) (setq ends (cons ep ends))))
  (setq ends (reverse ends))
  (EL:PerfEnd batch 'returned)
  (EL:PerfCount "start-snapshot-source-wires" (length (EL:Get 'wires snapshot)))
  (EL:PerfCount "start-snapshot-kept-wires" (length kept))
  (EL:PerfCount "start-snapshot-removed-wires" (length removed))
  (EL:PerfCount "start-snapshot-ends" (length ends))
  (setq result (EL:Put 'circuit-starts starts (EL:Put 'start-boundary-source (reverse removed)
    (EL:Put 'wires kept (EL:Put 'ends ends snapshot)))))
  (if (assoc 'source-wire-ids result)
    (progn
      (setq removed-ids (mapcar '(lambda (wire) (EL:Get 'id wire)) removed))
      (setq result (EL:Put 'source-wire-ids
        (vl-remove-if '(lambda (id) (member id removed-ids)) (EL:Get 'source-wire-ids result)) result))))
  (EL:PerfEnd perf 'returned) result)
;; Date: 2026-10-10. Infer wire style from actual panel contacts.
;; Date: 2026-10-10. A selected trunk is a logical panel boundary, never a circuit edge.
(defun EL:TrunkPoint (point segments)
  (and segments (EL:Touches point segments (EL:GapEpsilon) (EL:GapEpsilon))))
(defun EL:TrunkCross (segment edge / a b c d u v delta det fraction other point)
  (setq a (car segment) b (cadr segment) c (car edge) d (cadr edge)
    u (EL:V- b a) v (EL:V- d c) delta (EL:V- c a)
    det (- (* (car u) (cadr v)) (* (cadr u) (car v))))
  (if (> (abs det) 1.0e-12)
    (progn
      (setq fraction (/ (- (* (car delta) (cadr v)) (* (cadr delta) (car v))) det)
        other (/ (- (* (car delta) (cadr u)) (* (cadr delta) (car u))) det)
        point (EL:V+ a (EL:V* fraction u)))
      (if (and (>= fraction 0.0) (<= fraction 1.0) (>= other 0.0) (<= other 1.0)
          (<= (abs (- (caddr point) (caddr (EL:V+ c (EL:V* other v))))) (EL:GapEpsilon))) point))))
(defun EL:TrunkPiece (wire segments index / id points)
  (setq id (strcat (EL:Get 'id wire) "~C" (itoa index))
    points (cons (caar segments) (mapcar 'cadr segments)))
  (EL:PrepareWireBounds (EL:Put 'contact-strips (EL:WireContactStrips segments (EL:Get 'width-profiles wire))
  (EL:Put 'source-wire (EL:Get 'id wire)
    (EL:Put 'id id (EL:Put 'segments segments (EL:Put 'bounds (EL:SegmentBounds segments)
      (EL:Put 'ends (list (EL:MakeEnd id 'start points nil (EL:Get 'layer wire))
         (EL:MakeEnd id 'end points nil (EL:Get 'layer wire))) wire))))))))
(defun EL:TrunkSplitWire (wire trunk / segment edge point points parts current a b index out)
  (foreach segment (EL:Get 'segments wire)
    (setq points (list (car segment) (cadr segment)))
    (foreach edge trunk
      (if (setq point (EL:TrunkCross segment edge)) (setq points (cons point points))))
    (setq points (vl-sort (EL:Unique points)
      '(lambda (a b) (< (EL:Norm (EL:V- a (car segment))) (EL:Norm (EL:V- b (car segment)))))))
    (while (cdr points)
      (setq a (car points) b (cadr points) points (cdr points))
      (if (> (EL:Norm (EL:V- b a)) (EL:GapEpsilon))
        (progn
          (EL:Require (not (and (EL:TrunkPoint a trunk) (EL:TrunkPoint b trunk)
            (EL:TrunkPoint (EL:V* 0.5 (EL:V+ a b)) trunk)))
            "存在与集中干线重叠的导线，请清理重叠后重试。")
          (setq current (append current (list (list a b))))
          (if (EL:TrunkPoint b trunk)
            (setq parts (append parts (list current)) current nil))))))
  (if current (setq parts (append parts (list current))))
  (if (= (length parts) 1) (list wire)
    (progn
      (setq index 0)
      (foreach current parts
        (setq index (1+ index) out (cons (EL:TrunkPiece wire current index) out)))
      (reverse out))))
(defun EL:TrunkSnapshot (snapshot cfg panel / trunk block wires wire piece feeder ends shape roots)
  (setq trunk (EL:By 'id (EL:Get 'concentrated-trunk cfg) (EL:Get 'wires snapshot))
    block (EL:By 'id panel (EL:Get 'blocks snapshot)))
  (EL:Require (and trunk block (not (EL:Get 'issues trunk)))
    "集中干线或关联配电箱缺失、改变图层或几何无效，请重新拾取。")
  (foreach wire (EL:Get 'wires snapshot)
    (if (not (equal (EL:Get 'id wire) (EL:Get 'id trunk)))
      (foreach piece (EL:TrunkSplitWire wire (EL:Get 'segments trunk))
        (EL:Require (not (vl-every '(lambda (ep) (EL:TrunkPoint (EL:Get 'point ep) (EL:Get 'segments trunk)))
          (EL:Get 'ends piece))) "导线两端均接回集中干线，无法确定独立回路，请核对。")
        (if (and (vl-some '(lambda (ep) (EL:TrunkPoint (EL:Get 'point ep) (EL:Get 'segments trunk)))
              (EL:Get 'ends piece)) (EL:PathBlockHit piece block cfg))
          (setq feeder (cons piece feeder))
          (progn (setq wires (cons piece wires))
            (if (vl-some '(lambda (ep) (EL:TrunkPoint (EL:Get 'point ep) (EL:Get 'segments trunk)))
                  (EL:Get 'ends piece)) (setq roots (cons (EL:Get 'id piece) roots))))))))
  (EL:Require (= (length feeder) 1)
    "未找到唯一的箱体到集中干线连接段，请核对箱体及连接线；不按距离猜测。")
  (EL:Require roots "集中干线上未找到独立出线。")
  (setq wires (reverse wires))
  (foreach wire wires (setq ends (append ends (EL:Get 'ends wire))))
  (setq shape (list (cons 'id panel) (cons 'name (EL:Get 'name block)) '(role . panel)
    (cons 'entity (EL:Get 'entity block)) (cons 'layer (EL:Get 'layer block))
    (cons 'segments (EL:Get 'segments trunk)) (cons 'bounds (EL:SegmentBounds (EL:Get 'segments trunk)))))
  (EL:Put 'trunk-source (list trunk block feeder)
    (EL:Put 'trunk-roots roots (EL:Put 'trunk-segments (EL:Get 'segments trunk)
      (EL:Put 'wires wires (EL:Put 'ends ends
        (EL:Put 'blocks (subst shape block (EL:Get 'blocks snapshot)) snapshot)))))))
(defun EL:WireLayerStyle (layer / saved started lt)
  ;; Date: 2026-10-21. Only one synchronous collect shares layer lookups.
  (if (and *EL:WireLayerCacheEnabled* (not (equal *EL:WireLayerCacheEpoch* *EL:FreshEpoch*)))
    (setq *EL:WireLayerStyles* nil *EL:WireLayerCacheEpoch* *EL:FreshEpoch*))
  (if (and *EL:WireLayerCacheEnabled* (setq saved (assoc layer *EL:WireLayerStyles*)))
    (progn (setq *EL:WireLayerCacheHits* (1+ *EL:WireLayerCacheHits*)) (cdr saved))
    (progn
      (setq started (if *EL:WireLayerCacheEnabled* (EL:Tick))
        lt (strcase (cond ((cdr (assoc 6 (tblsearch "LAYER" layer)))) (T "CONTINUOUS"))))
      (if *EL:WireLayerCacheEnabled*
        (setq *EL:WireLayerStyles* (cons (cons layer lt) *EL:WireLayerStyles*)
          *EL:WireLayerReads* (1+ *EL:WireLayerReads*)
          *EL:WireLayerReadMS* (+ *EL:WireLayerReadMS* (EL:Elapsed started)))) lt)))
(defun EL:WireStyle (d / layer lt)
  (setq layer (cdr (assoc 8 d)) lt (strcase (cond ((cdr (assoc 6 d))) (T "BYLAYER"))))
  (if (equal lt "BYLAYER") (setq lt (EL:WireLayerStyle layer)))
  ;; Model-space entities have no parent INSERT from which to inherit ByBlock.
  (if (equal lt "BYBLOCK") (setq lt "CONTINUOUS"))
  (list layer lt))
(defun EL:WireStyleAllowed (d cfg)
  (and (member (cdr (assoc 8 d)) (EL:Get 'wire-layers cfg))
    (or (not (EL:Get 'wire-styles cfg)) (member (EL:WireStyle d) (EL:Get 'wire-styles cfg)))))
(defun EL:PanelContactShape (entity cfg / shape)
  (setq shape (EL:BlockContour entity '(1.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0)
    (EL:Get 'eps_boundary (EL:Get 'params cfg)) nil))
  (if (and (not (EL:Get 'issues shape)) (EL:Get 'segments shape))
    (EL:Put 'id (cdr (assoc 5 (entget entity)))
      (EL:Put 'regions (EL:ClosedRings (EL:Get 'segments shape)) shape))))
(defun EL:PanelWireCandidates (panel cfg / shape ss i e d wire rows)
  (setq shape (vl-catch-all-apply 'EL:PanelContactShape (list panel cfg)))
  (if (vl-catch-all-error-p shape) (setq shape nil))
  (if shape
    (progn
      (setq shape (EL:PrepareContactBlock shape)
        ss (EL:PresetSelection cfg "LINE,LWPOLYLINE" '(wire-layers)) i 0)
      (if ss
        (repeat (sslength ss)
          (setq e (ssname ss i) d (entget e) i (1+ i))
          (if (and (member (cdr (assoc 0 d)) '("LINE" "LWPOLYLINE"))
                   (not (equal (cdr (assoc 60 d)) 1)) (not (EL:ManagedEntity e))
                   (or (not (EL:Get 'preset-scoped cfg)) (EL:PresetMember (cdr (assoc 8 d)) (EL:Get 'wire-layers cfg))))
            (progn
              (setq wire (EL:WireRecord e cfg))
              (if (and (not (EL:Get 'issues wire)) (EL:Get 'ends wire)
                       (EL:PathBlockHit wire shape cfg))
                (setq rows (cons (list (cons 'entity e) (cons 'style (EL:WireStyle d))) rows)))))))))
  (list (cons 'shape shape) (cons 'candidates (reverse rows))))
(defun EL:PanelWireConfig (panel cfg / found rows styles row pick chosen d wire valid)
  (if (setq cfg (EL:PresetReady panel cfg))
    (progn
      (princ "\n正在从配电箱接线自动识别导线...")
      (setq found (EL:PanelWireCandidates panel cfg) rows (EL:Get 'candidates found))
      (foreach row rows (setq styles (cons (EL:Get 'style row) styles)))
      (setq styles (EL:Unique styles))
      (if (= (length styles) 1)
        (setq chosen (car styles))
        (progn
          (foreach row rows (EL:HighlightPick (EL:Get 'entity row)))
          (princ (if styles "\n箱口存在多种图层或线型，候选已高亮，请选择本系统导线。"
            "\n未能明确识别箱口导线，请补选本系统导线；不会按最近距离猜测。"))
          (while (and (not chosen) (setq pick (EL:PickModel 'wire "\n补选一条导线，Enter 取消：")))
            (setq d (entget (car pick)) wire (EL:WireRecord (car pick) cfg)
              valid (and (or (not (EL:Get 'preset-scoped cfg)) (EL:PresetMember (cdr (assoc 8 d)) (EL:Get 'wire-layers cfg))) (not (EL:ManagedEntity (car pick))) (not (EL:Get 'issues wire))
                (not (equal (cdr (assoc 60 d)) 1))))
            (if (and valid (or (not styles) (member (EL:WireStyle d) styles)))
              (setq chosen (EL:WireStyle d))
              (princ "\n请选择与箱口候选同图层、同线型的有效导线。")))))
      (EL:ClearPickHighlights)
      (if chosen
        (progn
          (princ (strcat "\n导线图层：" (car chosen) "；线型：" (cadr chosen)))
          (EL:LogEvent "AUTO_WIRE_STYLE" (list (cons 'candidates (mapcar '(lambda (r) (EL:LogEntity (EL:Get 'entity r))) rows))
            (cons 'styles styles) (cons 'chosen chosen)))
          (setq cfg (EL:Put 'wire-styles (list chosen) (EL:Put 'wire-layers (list (car chosen)) cfg)))
          (if (EL:Get 'shape found) (setq cfg (EL:Put 'auto-panel (cdr (assoc 5 (entget panel))) cfg)))
          cfg)))))
;; Date: 2026-10-10. One panel pick, connected devices, persistent power table.
(defun EL:SimpleBlockCandidates (wire tree cfg / candidates ep)
  (setq candidates (EL:SpatialBoxQuery tree (EL:WireContactBounds wire)
    (max (EL:Get 'eps_boundary (EL:Get 'params cfg)) (EL:DeviceContactTolerance cfg))))
  ;; Date: 2026-10-13. Collect gap devices for endpoint/contact checks and
  ;; source freshness even though virtual continuation does not connect them.
  (foreach ep (EL:Get 'ends wire)
    (if (EL:GapEligible ep)
      (setq candidates (append candidates (EL:SpatialRayQuery tree (EL:Get 'point ep)
        (EL:Get 'direction ep) (EL:Get 'Dmax (EL:Get 'params cfg)))))))
  candidates)

(defun EL:CollectBlockName (entity definition / saved name)
  ;; Date: 2026-10-15. Cache only the effective name of a block definition,
  ;; within one fresh collection. Instance geometry is always read separately.
  (if (and definition (setq saved (assoc definition *EL:CollectBlockNames*))) (cdr saved)
    (progn
      (setq name (EL:EffectiveName entity))
      (if definition (setq *EL:CollectBlockNames* (cons (cons definition name) *EL:CollectBlockNames*))) name)))
(setq *EL:CollectMemo* nil)
(defun EL:CollectRules (cfg)
  (vl-remove-if '(lambda (row) (equal (car row) 'template)) cfg))
(defun EL:CollectLayerFacts (cfg)
  (mapcar '(lambda (layer) (list layer (tblsearch "LAYER" layer))) (EL:Get 'wire-layers cfg)))
(defun EL:CandidateIndexPut (code child branches)
  ;; Compare only the bounded character keys, never whole growing subtrees.
  (cond ((not branches) (list (cons code child)))
    ((= code (car (car branches))) (cons (cons code child) (cdr branches)))
    (T (cons (car branches) (EL:CandidateIndexPut code child (cdr branches))))))
(defun EL:CandidateIndexInsert (codes node / branch child)
  ;; Date: 2026-10-21. A trie retains every character and a separate terminal
  ;; bit: handles sharing a prefix cannot collide. Native DXF handles have at
  ;; most sixteen different character branches; no COM dictionary or intern.
  (if codes
    (progn
      (setq *EL:CandidateIndexSteps* (1+ *EL:CandidateIndexSteps*)
        branch (assoc (car codes) (cdr node))
        child (EL:CandidateIndexInsert (cdr codes) (cdr branch)))
      (if *EL:CandidateIndexNew*
        (cons (car node) (EL:CandidateIndexPut (car codes) child (cdr node))) node))
    (if (car node) node
      (progn (setq *EL:CandidateIndexNew* T) (cons T (cdr node))))))
(defun EL:CandidateIndexAdd (id / *EL:CandidateIndexNew*)
  ;; Date: 2026-10-21. The caller owns the dynamic index for one collection.
  ;; Keep exact equality for malformed/non-string adapter keys as well; native
  ;; entity handles always use the bounded-character string path above.
  (setq *EL:CandidateIndexLookups* (1+ *EL:CandidateIndexLookups*))
  (if (equal (type id) 'STR)
    (setq *EL:CandidateIndex* (EL:CandidateIndexInsert (vl-string->list id) *EL:CandidateIndex*))
    (if (not (member id *EL:CandidateIndexOther*))
      (setq *EL:CandidateIndexOther* (cons id *EL:CandidateIndexOther*) *EL:CandidateIndexNew* T)))
  (if (not *EL:CandidateIndexNew*)
    (setq *EL:CandidateIndexDuplicates* (1+ *EL:CandidateIndexDuplicates*))) *EL:CandidateIndexNew*)
(defun EL:CandidateIndexMetrics ()
  ;; Date: 2026-10-21. Flush aggregate work once per batch, without per-ID logs.
  (EL:PerfCount "source-candidate-index-lookups" *EL:CandidateIndexLookups*)
  (EL:PerfCount "source-candidate-index-steps" *EL:CandidateIndexSteps*)
  (EL:PerfCount "source-candidate-index-duplicates" *EL:CandidateIndexDuplicates*)
  (setq *EL:CandidateIndexLookups* 0 *EL:CandidateIndexSteps* 0 *EL:CandidateIndexDuplicates* 0))
(defun EL:CollectSourceCurrent (cfg result / memo ss i e d facts fact good name saved *EL:CollectBlockNames*)
  ;; Date: 2026-10-15. Re-read the entire native selection, bounds, names and
  ;; panel contour. Equality skips derived wire/candidate calculations only.
  ;; Device contact definitions are still checked by NetworkGeometryCurrent.
  (setq memo *EL:CollectMemo*)
  (if (and memo (not *EL:NetworkReuseDisabled*)
      (equal (EL:Get 'owner memo) (namedobjdict))
      (equal (EL:Get 'signature memo) (EL:Get 'signature (EL:Get 'snapshot result)))
      (EL:Get 'signature memo)
      (equal (EL:Get 'drawing memo) (EL:DrawingID))
      (equal (EL:Get 'config memo) (EL:CollectRules cfg))
      (equal (EL:Get 'layers memo) (EL:CollectLayerFacts cfg)))
    (progn
      (setq ss (EL:PresetSelection cfg "INSERT,LINE,LWPOLYLINE" '(wire-layers panel-layers device-layers))
        facts (EL:Get 'facts memo) i 0 good T)
      (while (and good ss (< i (sslength ss)))
        (setq e (ssname ss i) d (entget e '("EL_FIXED_V1")) i (1+ i))
        (EL:PerfCount "source-native-entity-checks" 1)
        (if (not (cdr (assoc "EL_FIXED_V1" (cdr (assoc -3 d)))))
          (progn
            (setq fact (car facts) facts (cdr facts)
              good (and fact (equal d (car fact))))
            (if (and good (cadr fact))
              (progn
                (EL:PerfCount "source-native-bounds-checks" 1)
                (setq good (equal (cadr fact) (EL:EntityBounds e)))))
            (if (and good (equal (cdr (assoc 0 d)) "INSERT")
                (setq saved (assoc (cdr (assoc 2 d)) (EL:Get 'names memo))))
              (setq good (equal (cdr saved) (EL:CollectBlockName e (cdr (assoc 2 d)))))))))
      (setq good (and good (not facts)))
      (if (and good (EL:Get 'auto-panel cfg))
        (setq good (equal (EL:Get 'panel-shape memo)
          (EL:PanelContactShape (handent (EL:Get 'auto-panel cfg)) cfg))))
      (if good (progn (EL:PerfCount "source-derived-reuses" 1) (EL:Get 'input memo))))))
;; Date: 2026-10-21. Explicit-root collection owns all deferred state locally.
(defun EL:SimpleCollect (cfg / result owner epoch *EL:RootScopeCollecting* *EL:RootScopePanelShape* *EL:RootScopeOriginalWires* *EL:RootScopeResolvedWires*)
  (setq *EL:RootScopeCollecting* (and (EL:Get 'auto-panel cfg) (EL:Get 'circuit-starts cfg) (EL:CircuitStartsValid (EL:Get 'circuit-starts cfg))))
  (if *EL:RootScopeCollecting* (setq owner (namedobjdict) epoch *EL:FreshEpoch*))
  (setq result (EL:SimpleCollectFull cfg))
  ;; Include native candidate reads and order reconstruction in the same guard.
  (if (and *EL:RootScopeCollecting*
      (not (and (equal owner (namedobjdict)) (equal epoch *EL:FreshEpoch*))))
    (progn
      (setq *EL:CollectMemo* nil *EL:NetworkMemo* nil)
      (EL:Require nil "SOURCE_CHANGED：按需收集期间发生写入、交互或切图，请重新统计。"))) result)
(defun EL:RootScopeResolve (wire / id saved data full)
  (if (and *EL:RootScopeActive* wire)
    (progn
      (setq id (EL:Get 'id wire))
      (if (setq saved (assoc id *EL:RootScopeFineRecords*)) (cdr saved)
        (progn
          (if (assoc 'deferred-dxf wire)
            (progn
              (setq data (EL:Get 'deferred-dxf wire))
              (EL:PerfCount "source-wire-record-reads" 1)
              (EL:PerfCount "root-scope-wire-materializations" 1)
              (setq full (EL:WireRecordDXF (EL:Get 'entity wire)
                (vl-remove-if '(lambda (row) (= (car row) -3)) data) *EL:WalkConfig*)))
            (setq full wire))
          (setq *EL:RootScopeFineRecords* (cons (cons id full) *EL:RootScopeFineRecords*)) full)))
    wire))
(defun EL:RootScopeGapIndex (a b snapshot / p q direction distance wires item)
  ;; A rejected/non-reached wire may still block the gap. Read every corridor hit.
  (setq p (EL:Get 'point a) q (EL:Get 'point b)
    direction (EL:Unit (EL:V- q p)) distance (EL:Norm (EL:V- q p)))
  (foreach item (EL:SpatialRayQuery *EL:WalkWireTree* p direction distance)
    (setq wires (cons (EL:RootScopeResolve (EL:Get 'wire item)) wires)))
  (EL:GapPathIndex (EL:Put 'wires (reverse wires) snapshot)))
(defun EL:RootScopeOrder (blocks tree cfg / targets items block wire probe candidates candidate id seen ordered queue current data perf reads saved)
  ;; Date: 2026-10-21. Unreached wires may have seeded the old candidate order.
  ;; Reconstruct only the retained bbox component. Straight zero-width probes
  ;; use exact raw bounds; nearby curved/wide order dependencies are read fresh.
  (setq perf (EL:PerfBegin "ROOT_SCOPE_CANDIDATE_ORDER") reads 0)
  (foreach block blocks
    (setq id (EL:Get 'id block) targets (cons (cons id block) targets)
      items (cons (list (cons 'key id) (cons 'bounds (EL:Get 'bounds block))
        (cons 'point (EL:V* 0.5 (EL:V+ (car (EL:Get 'bounds block)) (cadr (EL:Get 'bounds block)))))) items)))
  (setq items (EL:SpatialTree items 0))
  (foreach wire *EL:RootScopeOriginalWires*
    (setq saved (assoc (EL:Get 'id wire) *EL:RootScopeResolvedWires*)
      probe (cond (saved (cdr saved)) ((EL:Get 'candidate-bounds wire)
        (EL:Put 'contact-bounds (EL:Get 'candidate-bounds wire) wire)) (T wire)))
    (if (EL:SimpleBlockCandidates probe items cfg)
      (progn
        (if (and (assoc 'deferred-dxf probe) (not (EL:Get 'candidate-bounds probe)))
          (progn
            (setq data (EL:Get 'deferred-dxf probe) reads (1+ reads))
            (EL:PerfCount "source-wire-record-reads" 1)
            (setq probe (EL:WireRecordDXF (EL:Get 'entity probe)
              (vl-remove-if '(lambda (row) (= (car row) -3)) data) cfg))))
        ;; Query the original full tree, retaining its exact result order.
        (foreach candidate (EL:SimpleBlockCandidates probe tree cfg)
          (setq id (EL:Get 'key candidate))
          (if (and (assoc id targets) (not (member id seen)))
            (setq seen (cons id seen) ordered (cons (cdr (assoc id targets)) ordered)))))))
  (setq queue ordered)
  (while queue
    (setq current (car queue) queue (cdr queue))
    (foreach candidate (EL:SpatialBoxQuery tree (EL:Get 'bounds current) (EL:DeviceContactTolerance cfg))
      (setq id (EL:Get 'key candidate))
      (if (and (assoc id targets) (not (member id seen)))
        (setq seen (cons id seen) block (cdr (assoc id targets))
          ordered (cons block ordered) queue (cons block queue)))))
  (EL:Require (= (length ordered) (length blocks)) "按需候选顺序复核失败，请保留诊断日志。")
  (EL:PerfCount "root-scope-order-wire-reads" reads)
  (EL:PerfEnd perf 'returned) ordered)
(defun EL:RootScopeDiscover (wires candidates cfg / snapshot original wire item block blocks items ends ep row id bounds point roots output perf batchperf owner epoch
    *EL:RootScopeActive* *EL:RootScopeFineRecords*
    *EL:WalkPanel* *EL:WalkConfig* *EL:WalkSnapshot* *EL:WalkTouch*
    *EL:WalkWireTree* *EL:WalkBlockTree* *EL:WalkEndTree* *EL:WalkJunctionTree*
    *EL:WalkWireRecords* *EL:WalkBlockRecords* *EL:WalkEndRecords*
    *EL:WalkQueue* *EL:WalkSeen* *EL:WalkEdges* *EL:WalkEnds* *EL:WalkGapRows* *EL:WalkContactHits*
    *EL:WalkGapSnapshot* *EL:GapPathIndex* *EL:GapIndexReady* *EL:DeviceContactTolerance*
    *EL:DeviceContactCache* *EL:DeviceTemplateCache* *EL:DeviceTemplateEnabled*)
  (setq perf (EL:PerfBegin "ROOT_SCOPE_DISCOVERY") owner (namedobjdict) epoch *EL:FreshEpoch*
    *EL:RootScopeActive* T *EL:WalkConfig* cfg *EL:WalkPanel* (EL:Get 'auto-panel cfg)
    *EL:WalkTouch* (EL:Get 'eps_touch (EL:Get 'params cfg))
    *EL:DeviceContactTolerance* (EL:DeviceContactTolerance cfg) *EL:DeviceTemplateEnabled* T
    original wires roots (mapcar '(lambda (row) (EL:Get 'wire row)) (EL:Get 'circuit-starts cfg)))
  ;; Date: 2026-10-21. Fixed batch clocks only; preserve every query and walk order.
  ;; Preserve the real panel contour and whole native INSERT bounds.
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_PANEL_SHAPE"))
  (if *EL:WalkPanel*
    (setq *EL:RootScopePanelShape* (EL:PanelContactShape (handent *EL:WalkPanel*) cfg)))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_BLOCK_RECORDS"))
  (foreach item candidates
    (setq id (EL:Get 'key item)
      block (list (cons 'entity (EL:Get 'entity item)) (cons 'id id)
        (cons 'name (cond ((EL:Get 'name item))
          (T (EL:CollectBlockName (EL:Get 'entity item) (EL:Get 'definition-name item)))))
        (cons 'layer (EL:Get 'layer item))
        (cons 'bounds (EL:Get 'bounds item)) (cons 'whole-block T)))
    (if (and (equal id *EL:WalkPanel*) *EL:RootScopePanelShape*)
      (setq block (append (EL:Put 'whole-block nil block) *EL:RootScopePanelShape*)))
    (setq block (EL:Put 'role (EL:FixedBlockRole block *EL:WalkPanel* cfg) block)
      blocks (cons block blocks)))
  (EL:PerfEnd batchperf 'returned)
  ;; Materialize picked roots and every possible source-side boundary contact.
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_ROOT_PREPARE"))
  (foreach wire wires
    (if (or (not (assoc 'deferred-dxf wire)) (member (EL:Get 'id wire) roots)
        (vl-some '(lambda (row)
          (EL:InBounds (EL:Get 'point row) (EL:StartBoundaryBounds wire *EL:WalkTouch*) 0.0))
          (EL:Get 'circuit-starts cfg)))
      (setq wire (EL:RootScopeResolve wire)))
    (setq output (cons wire output))
    (foreach ep (EL:Get 'ends wire) (setq ends (cons ep ends))))
  (setq snapshot (list (cons 'wires (reverse output)) (cons 'blocks blocks) (cons 'ends (reverse ends))))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_START_SNAPSHOT"))
  (setq snapshot (EL:StartSnapshot snapshot cfg *EL:WalkPanel*)
    *EL:WalkSnapshot* snapshot wires (EL:Get 'wires snapshot))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_WIRE_INDEX"))
  (foreach wire wires
    (setq id (EL:Get 'id wire) bounds (EL:WireContactBounds wire)
      *EL:WalkWireRecords* (cons (cons id wire) *EL:WalkWireRecords*))
    (if bounds
      (setq items (cons (list (cons 'key id) (cons 'wire wire) (cons 'bounds bounds)
        (cons 'point (EL:V* 0.5 (EL:V+ (car bounds) (cadr bounds))))) items))))
  (setq *EL:WalkWireTree* (EL:SpatialTree items 0) items nil)
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_BLOCK_INDEX"))
  (foreach block blocks
    (setq id (EL:Get 'id block) bounds (EL:Get 'bounds block)
      *EL:WalkBlockRecords* (cons (cons id block) *EL:WalkBlockRecords*)
      items (cons (list (cons 'key id) (cons 'block block) (cons 'bounds bounds)
        (cons 'point (EL:V* 0.5 (EL:V+ (car bounds) (cadr bounds))))) items)))
  (setq *EL:WalkBlockTree* (EL:SpatialTree items 0))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_JUNCTION_INDEX"))
  (setq *EL:WalkJunctionTree* (EL:JunctionTree blocks))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_END_INDEX"))
  (setq *EL:WalkEndTree* (EL:SpatialTree (mapcar '(lambda (ep)
      (EL:Put 'bounds (list (EL:Get 'point ep) (EL:Get 'point ep)) ep)) (EL:Get 'ends snapshot)) 0))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_GAP_SNAPSHOT"))
  (setq *EL:WalkGapSnapshot* (EL:SimpleGapSnapshot snapshot))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_ROOT_LINKS"))
  (foreach ep (EL:Get 'ends snapshot)
    (setq *EL:WalkEndRecords* (cons (cons (EL:Get 'key ep) ep) *EL:WalkEndRecords*)))
  (foreach wire wires
    (if (member (EL:Get 'id wire) roots) (EL:WalkLink *EL:WalkPanel* (EL:Get 'id wire))))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_REACHABLE_TRACE"))
  (while *EL:WalkQueue*
    (setq id (car *EL:WalkQueue*) *EL:WalkQueue* (cdr *EL:WalkQueue*))
    (if (not (member id *EL:WalkSeen*))
      (progn
        (setq *EL:WalkSeen* (cons id *EL:WalkSeen*))
        (if (setq wire (cdr (assoc id *EL:WalkWireRecords*)))
          (EL:WalkWire (EL:RootScopeResolve wire))
          (if (setq block (cdr (assoc id *EL:WalkBlockRecords*))) (EL:WalkBlock block))))))
  (EL:PerfEnd batchperf 'returned)
  (setq batchperf (EL:PerfBegin "ROOT_SCOPE_RESULT_ORDER"))
  (setq output nil)
  ;; Keep native relative order, including tested misses and gap competitors.
  (foreach wire original
    (if (setq item (assoc (EL:Get 'id wire) *EL:RootScopeFineRecords*))
      (setq output (cons (cdr item) output))))
  (EL:Require (and (equal owner (namedobjdict)) (equal epoch *EL:FreshEpoch*))
    "SOURCE_CHANGED：按需识别期间发生写入、交互或切图，请重新统计。")
  (EL:PerfCount "root-scope-light-wires" (length original))
  (EL:PerfCount "root-scope-fine-wires" (length output))
  (EL:PerfCount "root-scope-skipped-wires" (- (length original) (length output)))
  (EL:LogEvent "ROOT_SCOPE_DISCOVERED" (list (cons 'source-wires (length original))
    (cons 'fine-wires (length output)) (cons 'walk-objects (length *EL:WalkSeen*))
    (cons 'policy 'exact-root-dependencies)))
  (setq output (reverse output))
  (EL:PerfEnd batchperf 'returned)
  (EL:PerfEnd perf 'returned) output)
(defun EL:SimpleCollectFull (cfg / ss i e d bounds items tree wires ends blocks wire candidate id issues block queue current shape perf candidateperf name facts snapshot
    *EL:CollectBlockNames* *EL:CandidateIndex* *EL:CandidateIndexOther*
    *EL:CandidateIndexLookups* *EL:CandidateIndexSteps* *EL:CandidateIndexDuplicates*
    *EL:WireLayerCacheEnabled* *EL:WireLayerStyles* *EL:WireLayerCacheEpoch*
    *EL:WireLayerCacheHits* *EL:WireLayerReads* *EL:WireLayerReadMS*
    *EL:PresetCacheEnabled* *EL:PresetCacheCfg* *EL:PresetCacheEpoch* *EL:PresetCacheTables* *EL:PresetCacheBlocks*
    *EL:PresetCacheHits* *EL:PresetCacheMisses* *EL:PresetCacheNormalizations*
    *EL:PresetCacheMemberHits* *EL:PresetCacheMemberMisses* *EL:PresetCacheRebuilds* *EL:PresetCacheCheckMS*
    *EL:CollectReadProfile* *EL:CollectDXFMS* *EL:CollectBoundsMS* *EL:CollectWireMS* *EL:CollectProfileReads* readstarted
    typ source-inserts source-lines source-polylines source-other source-managed source-rejected source-wire-ids
    root-proxies root-fallbacks root-reasons root-samples root-reason root-row root-discovery root-total-reasons root-total-row
    *EL:RootScopeFallbackReason* *EL:RootScopeFallbackError*)
  ;; Date: 2026-10-10. Filter wires by inferred style; only the selected panel
  ;; uses its contour. Device geometry is checked lazily during network tracing.
  ;; Date: 2026-10-20. Retain the actual pre-filter scope in diagnostic exports.
  (EL:LogEvent "RECOGNITION_SCOPE" (mapcar '(lambda (key) (cons key (EL:Get key cfg)))
    '(preset-scoped panel-layers panel-names wire-layers device-layers device-names)))
  (setq ss (EL:PresetSelection cfg "INSERT,LINE,LWPOLYLINE" '(wire-layers panel-layers device-layers)) i 0
    *EL:CandidateIndexLookups* 0 *EL:CandidateIndexSteps* 0 *EL:CandidateIndexDuplicates* 0
    *EL:WireLayerCacheEnabled* T *EL:WireLayerCacheEpoch* *EL:FreshEpoch*
    *EL:WireLayerCacheHits* 0 *EL:WireLayerReads* 0 *EL:WireLayerReadMS* 0
    *EL:PresetCacheEnabled* T *EL:PresetCacheHits* 0 *EL:PresetCacheMisses* 0 *EL:PresetCacheNormalizations* 0
    *EL:PresetCacheMemberHits* 0 *EL:PresetCacheMemberMisses* 0 *EL:PresetCacheRebuilds* 0 *EL:PresetCacheCheckMS* 0
    *EL:CollectReadProfile* (and *EL:PerfActive* (EL:CollectReadDetailEnabled)) *EL:CollectDXFMS* 0 *EL:CollectBoundsMS* 0 *EL:CollectWireMS* 0 *EL:CollectProfileReads* 0
    source-inserts 0 source-lines 0 source-polylines 0 source-other 0 source-managed 0 source-rejected 0
    root-proxies 0 root-fallbacks 0)
  ;; Date: 2026-10-21. Tables and positive/negative block decisions live only here.
  (EL:PerfCall "COLLECT_PRESET_PREPARE" 'EL:PresetCachePrepare (list cfg))
  (EL:PerfCount "source-collect-calls" 1)
  (EL:PerfCount "source-selection-entities" (if ss (sslength ss) 0))
  (setq perf (EL:PerfBegin "COLLECT_ENTITY_READ"))
  (if ss
    (repeat (sslength ss)
       (setq e (ssname ss i))
       (if *EL:CollectReadProfile* (setq readstarted (EL:Tick)))
       (setq d (entget e '("EL_FIXED_V1")))
       (if *EL:CollectReadProfile*
         (setq *EL:CollectDXFMS* (+ *EL:CollectDXFMS* (EL:PerfDelta readstarted (EL:Tick)))
           *EL:CollectProfileReads* (+ *EL:CollectProfileReads* 2)))
       (setq i (1+ i) id (cdr (assoc 5 d)) name nil bounds nil typ (cdr (assoc 0 d))
            *EL:SimpleEntity* (list id typ (cdr (assoc 8 d))))
      ;; Date: 2026-10-21. Count native objects in the existing read loop,
      ;; before filtering. These are not the selected panel's connected result.
      (cond ((equal typ "INSERT") (setq source-inserts (1+ source-inserts)))
        ((equal typ "LINE") (setq source-lines (1+ source-lines)))
        ((equal typ "LWPOLYLINE") (setq source-polylines (1+ source-polylines)))
        (T (setq source-other (1+ source-other))))
      (cond
        ;; The same selective native read includes the managed-output marker.
        ((cdr (assoc "EL_FIXED_V1" (cdr (assoc -3 d)))) (setq source-managed (1+ source-managed)))
        ((and (equal typ "INSERT")
            (or (not (EL:Get 'preset-scoped cfg))
              (EL:PresetBlockNameAllowed (setq name (EL:CollectBlockName e (cdr (assoc 2 d)))) d cfg)))
          (EL:PerfCount "source-block-bounds-reads" 1)
          (if (setq bounds (EL:EntityBounds e))
            (setq items (cons (list (cons 'key id) (cons 'entity e) (cons 'layer (cdr (assoc 8 d)))
              (cons 'name name) (cons 'definition-name (cdr (assoc 2 d)))
              (cons 'bounds bounds) (cons 'point (EL:V* 0.5 (EL:V+ (car bounds) (cadr bounds))))) items))
            (setq issues (cons (EL:Issue 'MISSING_BLOCK_BOUNDS id nil) issues))))
        ((equal typ "INSERT") (setq source-rejected (1+ source-rejected)))
        ((EL:WireStyleAllowed d cfg)
          (setq wire (if *EL:RootScopeCollecting* (EL:RootScopeWire e d cfg)))
          (if wire (setq root-proxies (1+ root-proxies))
            (progn
              (EL:PerfCount "source-wire-record-reads" 1)
              (if *EL:RootScopeCollecting*
                (progn
                  (setq root-fallbacks (1+ root-fallbacks)
                    root-reason (cond (*EL:RootScopeFallbackReason*) (T "unclassified")))
                  (if (setq root-row (assoc root-reason root-reasons))
                    (setq root-reasons (subst (cons root-reason (1+ (cdr root-row))) root-row root-reasons))
                    (progn
                      (setq root-reasons (cons (cons root-reason 1) root-reasons))
                      (if (< (length root-samples) 3)
                        (setq root-samples (cons (list (cons 'reason root-reason) (cons 'wire id)
                          (cons 'type typ) (cons 'error *EL:RootScopeFallbackError*)) root-samples)))))))
              (setq wire (EL:WireRecordDXF e (if (assoc -3 d)
                (vl-remove-if '(lambda (row) (= (car row) -3)) d) d) cfg))))
          (setq source-wire-ids (cons (EL:Get 'id wire) source-wire-ids) wires (cons wire wires)
            ends (append (EL:Get 'ends wire) ends) issues (append (EL:Get 'issues wire) issues))))
      (if (not (cdr (assoc "EL_FIXED_V1" (cdr (assoc -3 d)))))
        (setq facts (cons (list d bounds) facts)))))
  (EL:PerfCount "source-selection-inserts" source-inserts)
  (EL:PerfCount "source-selection-lines" source-lines)
  (EL:PerfCount "source-selection-polylines" source-polylines)
  (EL:PerfCount "source-selection-other" source-other)
  (EL:PerfCount "source-selection-managed-outputs" source-managed)
  (EL:PerfCount "source-rejected-block-inserts" source-rejected)
  ;; Date: 2026-10-21. Detail is explicit; disabled milliseconds are unmeasured.
  ;; Keep batch frames in every mode, and never write a per-entity log.
  (EL:PerfSet "source-read-profile-enabled" (if *EL:CollectReadProfile* 1 0))
  (EL:PerfCount "source-native-dxf-ms" *EL:CollectDXFMS*)
  (EL:PerfCount "source-block-bounds-ms" *EL:CollectBoundsMS*)
  (EL:PerfCount "source-wire-record-ms" *EL:CollectWireMS*)
  (EL:PerfCount "source-read-profile-clock-reads" *EL:CollectProfileReads*)
  (setq *EL:CollectReadProfile* nil)
  ;; Aggregate only; never add a measured frame or log write per wire.
  (EL:PerfCount "source-wire-layer-reads" *EL:WireLayerReads*)
  (EL:PerfCount "source-wire-layer-cache-hits" *EL:WireLayerCacheHits*)
  (EL:PerfCount "source-wire-layer-read-ms" *EL:WireLayerReadMS*)
  (EL:PresetCacheMetrics)
  (EL:PerfEnd perf 'returned)
  ;; Date: 2026-10-21. Publish bounded fallback diagnostics once per collection.
  ;; Keep the rooted source-facts guard even when every wire uses eager geometry.
  (if *EL:RootScopeCollecting*
    (progn
      (EL:PerfCount "root-scope-proxy-wires" root-proxies)
      (EL:PerfCount "root-scope-wire-fallbacks" root-fallbacks)
      (if *EL:PerfActive*
        (progn
          (setq root-total-reasons (EL:Get "root-scope-fallback-reasons" *EL:PerfMetrics*))
          (foreach root-row root-reasons
            (if (setq root-total-row (assoc (car root-row) root-total-reasons))
              (setq root-total-reasons (subst
                (cons (car root-row) (+ (cdr root-total-row) (cdr root-row))) root-total-row root-total-reasons))
              (setq root-total-reasons (append root-total-reasons (list root-row)))))
          (EL:PerfSet "root-scope-fallback-reasons" root-total-reasons)))
      (if (> root-fallbacks 0)
        (EL:LogEvent "ROOT_SCOPE_FALLBACKS" (list (cons 'fallback-wires root-fallbacks)
          (cons 'proxy-wires root-proxies) (cons 'reasons (reverse root-reasons))
          (cons 'samples (reverse root-samples)))))
      (setq root-discovery (> root-proxies 0))
      (if root-discovery
        (progn
          (setq *EL:RootScopeOriginalWires* wires
            wires (EL:RootScopeDiscover wires items cfg)
            *EL:RootScopeResolvedWires* (mapcar '(lambda (wire) (cons (EL:Get 'id wire) wire)) wires) ends nil)
          (foreach wire wires
            (foreach candidate (EL:Get 'ends wire) (setq ends (cons candidate ends)))
            (foreach candidate (EL:Get 'issues wire)
              (if (not (member candidate issues)) (setq issues (cons candidate issues)))))
          (setq ends (reverse ends)))
        (progn
          ;; Eager records already preserve the old candidate order and geometry.
          ;; Do not repeat discovery or reconstruct that same order a second time.
          (EL:PerfCount "root-scope-light-wires" (length wires))
          (EL:PerfCount "root-scope-fine-wires" (length wires))
          (if (> root-fallbacks 0) (EL:PerfCount "root-scope-all-fallback-bypass" 1))
          (EL:LogEvent "ROOT_SCOPE_BYPASSED" (list
            (cons 'reason (if (> root-fallbacks 0) 'all-wire-fallbacks 'no-source-wires))
            (cons 'source-wires (length wires)) (cons 'policy 'eager-collection)))))))
  (setq perf (EL:PerfBegin "COLLECT_CANDIDATES") candidateperf (EL:PerfBegin "COLLECT_SPATIAL_TREE")
    tree (EL:SpatialTree items 0))
  (EL:PerfEnd candidateperf 'returned)
  ;; The batch includes the unchanged wire box/ray queries and block records,
  ;; rather than timing/logging every individual membership operation.
  (setq candidateperf (EL:PerfBegin "COLLECT_CANDIDATE_DEDUP"))
  (foreach wire wires
    (foreach candidate (EL:SimpleBlockCandidates wire tree cfg)
      (if (EL:CandidateIndexAdd (EL:Get 'key candidate))
        (progn
          (setq id (EL:Get 'key candidate) *EL:SimpleEntity* (list id 'block-name)
                block (list (cons 'entity (EL:Get 'entity candidate)) (cons 'id id)
                  (cons 'name (cond ((EL:Get 'name candidate))
                    (T (EL:CollectBlockName (EL:Get 'entity candidate) (EL:Get 'definition-name candidate)))))
                  (cons 'layer (EL:Get 'layer candidate)) (cons 'bounds (EL:Get 'bounds candidate)) (cons 'whole-block T)))
          (setq blocks (cons block blocks))))))
  (EL:CandidateIndexMetrics)
  (EL:PerfEnd candidateperf 'returned)
  ;; Date: 2026-10-10. Expand the candidate set along touching device chains.
  (setq queue blocks candidateperf (EL:PerfBegin "COLLECT_DEVICE_EXPAND"))
  (while queue
    (setq current (car queue) queue (cdr queue))
    (foreach candidate (EL:SpatialBoxQuery tree (EL:Get 'bounds current) (EL:DeviceContactTolerance cfg))
      (setq id (EL:Get 'key candidate))
      (if (EL:CandidateIndexAdd id)
        (progn
          (setq *EL:SimpleEntity* (list id 'block-name)
                block (list (cons 'entity (EL:Get 'entity candidate)) (cons 'id id)
                  (cons 'name (cond ((EL:Get 'name candidate))
                    (T (EL:CollectBlockName (EL:Get 'entity candidate) (EL:Get 'definition-name candidate)))))
                  (cons 'layer (EL:Get 'layer candidate)) (cons 'bounds (EL:Get 'bounds candidate)) (cons 'whole-block T))
                blocks (cons block blocks) queue (cons block queue))))))
  (EL:CandidateIndexMetrics)
  (EL:PerfEnd candidateperf 'returned)
  (if root-discovery
    (setq blocks (EL:RootScopeOrder blocks tree cfg)))
  (EL:PerfEnd perf 'returned)
  (if (EL:Get 'auto-panel cfg)
    (progn
      (setq id (EL:Get 'auto-panel cfg) block (EL:By 'id id blocks)
        shape (cond (*EL:RootScopePanelShape*) (T (EL:PanelContactShape (handent id) cfg))))
      (EL:Require shape "配电箱轮廓已变化或无法读取，请重新运行 ELSTAT 并核对箱口。")
      (if block
        (setq blocks (subst (append (EL:Put 'whole-block nil block) shape) block blocks)))))
  (EL:PerfCount "source-candidate-blocks" (length blocks))
  (EL:LogEvent "SOURCE_SELECTION_SCOPE" (list '(scope . model-selection) (cons 'preset-scoped (if (EL:Get 'preset-scoped cfg) T nil))
    (cons 'selected (+ source-inserts source-lines source-polylines source-other))
    (cons 'inserts source-inserts) (cons 'lines source-lines) (cons 'polylines source-polylines)
    (cons 'other source-other) (cons 'managed-outputs source-managed) (cons 'rejected-inserts source-rejected)
    (cons 'accepted-wire-records (length wires)) (cons 'candidate-blocks (length blocks))))
  (EL:LogEvent "SIMPLE_COUNTS" (list (cons 'wires (length wires)) (cons 'blocks (length blocks)) (cons 'issues issues)))
  (setq snapshot (list (cons 'drawing (EL:DrawingID)) (cons 'wires wires) (cons 'blocks blocks) (cons 'ends ends) (cons 'issues issues)))
  (if *EL:RootScopeCollecting*
    (setq snapshot (EL:Put 'source-wire-ids source-wire-ids
      (EL:Put 'source-selection-facts
        (mapcar '(lambda (fact) (list (EL:CanonicalVisibilityDXF (car fact)) (cadr fact))) (reverse facts)) snapshot))))
  (setq *EL:CollectMemo* (if (not issues) (list (cons 'owner (namedobjdict))
    (cons 'drawing (EL:DrawingID)) (cons 'config (EL:CollectRules cfg))
    (cons 'layers (EL:CollectLayerFacts cfg)) (cons 'facts (reverse facts))
    (cons 'names *EL:CollectBlockNames*) (cons 'panel-shape shape)))) snapshot)

(defun EL:SimpleEndState (ep tree cfg / point occupied candidate candidates)
  (setq point (EL:Get 'point ep) occupied (EL:Get 'occupied ep))
  (if (not occupied)
    (setq candidates (EL:SpatialBoxQuery tree (list point point)
      (max (EL:Get 'eps_boundary (EL:Get 'params cfg)) (EL:DeviceContactTolerance cfg)))))
  (while (and candidates (not occupied))
    (setq candidate (car candidates) candidates (cdr candidates))
    (if (EL:SimpleDevicePointHit point (EL:Get 'block candidate) cfg) (setq occupied T)))
  ;; Only this endpoint is occupied; a connection elsewhere on its wire does
  ;; not prevent a free broken end from continuing to its unique counterpart.
  (EL:Put 'wire-attached nil (EL:Put 'occupied occupied ep)))

(defun EL:SimpleGapLog (snapshot cfg rows pairs / ep count logged)
  (if *EL:LogActive*
    (progn
      (setq count 0 logged 0)
      (foreach ep (EL:Get 'ends snapshot)
        (if (not (EL:Get 'occupied ep))
          (progn
            (setq count (1+ count))
            (if (< logged 100)
              (progn
                (EL:LogEvent "SIMPLE_GAP_END" (list ep (EL:By 'key (EL:Get 'key ep) rows)))
                (setq logged (1+ logged)))))))
      (EL:LogEvent "SIMPLE_GAPS" (list (cons 'device-policy 'pass-through) (cons 'max-distance (EL:Get 'Dmax (EL:Get 'params cfg)))
        (cons 'open-ends count) (cons 'logged-ends logged) (cons 'omitted-ends (- count logged))
        (cons 'paired-gaps (length (EL:Get 'pairs pairs))))))))

;; Date: 2026-10-10. Bounds only select candidates; visible geometry proves contact.
(defun EL:GeometryFacts (shape)
  ;; Date: 2026-10-13. Exact geometry only; derived spatial trees are never evidence.
  (mapcar '(lambda (key) (cons key (EL:Get key shape)))
    '(segments curves regions holes hole-paths issues sampled-curves)))
(defun EL:DeviceContactEvidence (contacts / row shape key geometry definitions instances)
  ;; Keep each local definition once, plus exact instance transforms. No text signature.
  ;; Missed contacts are dependencies too and remain in this evidence pool.
  (foreach row contacts
    (setq shape (cdr row) key (cond ((EL:Get 'definition-key shape)) (T (list 'instance (car row))))
      geometry (cond ((EL:Get 'definition-geometry shape)) (T (EL:GeometryFacts shape))))
    (if (not (assoc key definitions)) (setq definitions (cons (cons key geometry) definitions)))
    (setq instances (cons (list (car row) key (EL:Get 'instance-transform shape)) instances)))
  (list '(version . 3)
    (cons 'templates (vl-sort definitions '(lambda (a b) (< (EL:Signature (car a)) (EL:Signature (car b))))))
    (cons 'instances (vl-sort instances '(lambda (a b) (< (car a) (car b)))))))
(defun EL:TranslateDeviceShape (shape offset / matrix)
  (setq matrix (list 1.0 0.0 0.0 1.0 (car offset) (cadr offset) (caddr offset) 1.0))
  (list (cons 'curves (EL:TranslateCurves (EL:Get 'curves shape) offset))
    (cons 'segments (EL:TransformSegments (EL:Get 'segments shape) matrix))
    (cons 'regions (mapcar '(lambda (ring) (EL:TransformSegments ring matrix)) (EL:Get 'regions shape)))
    (cons 'holes (mapcar '(lambda (ring) (EL:TransformSegments ring matrix)) (EL:Get 'holes shape)))
    (cons 'segment-bounds (mapcar '(lambda (point) (EL:V+ point offset)) (EL:Get 'segment-bounds shape)))
    (cons 'contact-template shape) (cons 'contact-offset offset) (cons 'contact-ready T)
    (cons 'definition-key (EL:Get 'definition-key shape))
    (cons 'definition-geometry (EL:Get 'definition-geometry shape))
    (cons 'issues (EL:Get 'issues shape))))
(defun EL:DeviceDefinitionFacts (name stack / header entity data rows nested)
  ;; Date: 2026-10-21. Exact typed source, including nested headers/flags.
  ;; Handles and owners identify objects, not visible definition geometry.
  (if (or (member name stack) (>= (length stack) 16)) (list 'recursive name)
    (progn
      (setq header (tblsearch "BLOCK" name) entity (cdr (assoc -2 header)))
      (while (and entity (/= (cdr (assoc 0 (entget entity))) "ENDBLK"))
        (setq data (vl-remove-if '(lambda (row) (member (car row) '(-1 5 330))) (entget entity)) nested nil)
        (if (equal (cdr (assoc 0 data)) "INSERT")
          (setq nested (EL:DeviceDefinitionFacts (cdr (assoc 2 data)) (cons name stack))))
        (setq rows (cons (list data nested) rows) entity (entnext entity)))
      (list (vl-remove-if '(lambda (row) (member (car row) '(-1 -2 5 330))) header) (reverse rows)))))
(defun EL:DeviceCacheContext ()
  (list (namedobjdict) *EL:FreshEpoch* (EL:DeviceContourTolerance)))
(defun EL:ExactCoordinateShift (value offset / moved virtual)
  ;; Date: 2026-10-21. Knuth TwoSum: zero residual proves exact addition.
  (setq moved (+ value offset) virtual (- moved value))
  (= (+ (- value (- moved virtual)) (- offset virtual)) 0.0))
(defun EL:PoseTranslationSafe (shape offset origin matrix / bounds points point moved good actual local world a b i)
  ;; Date: 2026-10-21. Prove exact translation, without changing any epsilon.
  ;; Large coordinates, nested/analytic mixes and any rounding use the old path.
  (setq bounds (EL:Get 'segment-bounds shape)
    local (EL:Get 'pose-local-segments shape) world (EL:Get 'segments shape)
    actual (EL:AffineCompose '(1.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0) matrix)
    good (and bounds local (not (EL:Get 'curves shape)) (= (length local) (length world))
      (equal (mapcar '(lambda (i) (nth i actual)) '(0 1 2 3 7))
        (mapcar '(lambda (i) (nth i (EL:Get 'pose-matrix shape))) '(0 1 2 3 7))))
    points (append bounds (list origin offset)))
  (foreach point points
    (if (vl-some '(lambda (value) (> (abs value) 1.0e6)) point) (setq good nil)))
  (foreach point bounds
    (setq moved (EL:V+ point offset))
    (if (or (vl-some '(lambda (value) (> (abs value) 1.0e6)) moved)
        (not (equal point (EL:V- moved offset) 1.0e-9))) (setq good nil)))
  ;; Exact WCS reproduction and exact addition are separate obligations.
  ;; Merely matching bounds, tolerances or angles is insufficient.
  (while (and good local)
    (setq a (car local) b (car world) local (cdr local) world (cdr world))
    (foreach i '(0 1)
      (setq point (nth i b) moved (EL:V+ point offset))
      (if (or (not (equal moved (EL:AffinePoint (nth i a) actual)))
          (not (vl-every '(lambda (ok) ok) (mapcar 'EL:ExactCoordinateShift point offset))))
        (setq good nil))))
  good)
(defun EL:TranslatePoseShape (shape offset)
  ;; The first instance's WCS rings, holes and spatial tree stay shared.
  (list (cons 'contact-template shape) (cons 'contact-offset offset)
    (cons 'contact-ready T) (cons 'contact-lazy T)
    (cons 'curves (EL:TranslateCurves (EL:Get 'curves shape) offset))
    (cons 'segment-bounds (mapcar '(lambda (point) (EL:V+ point offset)) (EL:Get 'segment-bounds shape)))
    (cons 'sampled-curves (EL:Get 'sampled-curves shape))
    (cons 'definition-key (EL:Get 'definition-key shape))
    (cons 'definition-geometry (EL:Get 'definition-geometry shape))
    (cons 'issues (EL:Get 'issues shape))))
(defun EL:DeviceContactShape (block / id saved shape entity matrix key origin template context data definition local-shape reusable
    cache-context source definition-key pose-key offset started)
  (setq id (EL:Get 'id block) cache-context (EL:DeviceCacheContext)
    saved (assoc id *EL:DeviceContactCache*))
  (if (and saved (not (equal cache-context (EL:Get 'cache-context (cdr saved))))) (setq saved nil))
  (if saved (cdr saved)
    (progn
      (setq entity (cond ((EL:Get 'entity block)) (T (handent id)))
        data (entget entity)
        context (list (cons 'id id) (cons 'name (EL:Get 'name block)) (cons 'layer (EL:Get 'layer block))))
      (EL:ContactProgress "read" 0 context)
      (if *EL:DeviceTemplateEnabled*
        (progn
          (setq matrix (vl-catch-all-apply 'EL:InsertMatrix (list entity)))
          (if (and matrix (not (vl-catch-all-error-p matrix)))
            (progn
              (setq started (EL:Tick) source (EL:DeviceDefinitionFacts (cdr (assoc 2 data)) nil))
              (EL:PerfCount "device-definition-check-ms" (EL:Elapsed started))
              (setq definition-key (list 'definition cache-context (cdr (assoc 2 data)) source)
                pose-key (list 'pose-v1 (cdr (assoc 2 data))
                  (mapcar '(lambda (i) (nth i matrix)) '(0 1 2 3 7))
                  (mapcar '(lambda (code) (assoc code data)) '(41 42 43 50 210)) (EL:DeviceContourTolerance))
                key (list 'pose cache-context pose-key source)
                origin (list (nth 4 matrix) (nth 5 matrix) (nth 6 matrix))
                template (assoc key *EL:DeviceTemplateCache*))
              (if template
                (progn (setq offset (EL:V- origin (cadr template)) started (EL:Tick))
                  (if (and (EL:Get 'sampled-curves (caddr template))
                      (not (EL:PoseTranslationSafe (caddr template) offset origin matrix)))
                    (progn (setq template nil) (EL:PerfCount "device-pose-fallbacks" 1)))
                  (EL:PerfCount "device-pose-verify-ms" (EL:Elapsed started))))))))
      (if template
        (progn
          (EL:PerfCount "device-template-reuses" 1)
          (EL:PerfCount "device-pose-reuses" 1)
          (setq shape (if (EL:Get 'sampled-curves (caddr template))
            (EL:TranslatePoseShape (caddr template) offset)
            (EL:TranslateDeviceShape (caddr template) offset)))
          (EL:LogEvent "DEVICE_TEMPLATE_REUSE" context))
        (progn
          (if (and key (setq definition (assoc definition-key *EL:DeviceTemplateCache*)))
            (progn (setq local-shape (cadr definition)) (EL:PerfCount "device-definition-reuses" 1))
            (if key
              (progn
                (EL:PerfCount "device-contour-reads" 1)
                (setq started (EL:Tick))
                (setq local-shape (vl-catch-all-apply 'EL:DeviceDefinitionContour (list entity)))
                (EL:PerfCount "device-definition-build-ms" (EL:Elapsed started))
                ;; An interrupted definition probe cannot seed a successful pose.
                (if (vl-catch-all-error-p local-shape) (setq local-shape nil key nil))
                (if (and (EL:ShapeGeometry local-shape) (not (EL:Get 'issues local-shape)))
                  (progn
                    (setq *EL:DeviceTemplateCache* (cons (list definition-key local-shape)
                      *EL:DeviceTemplateCache*)))))))
          (if (and (EL:ShapeGeometry local-shape) (not (EL:Get 'issues local-shape)))
            (progn
              (setq shape (EL:TransformShape local-shape matrix) reusable (if shape 'definition))
              ;; Region tolerance is measured in WCS; scaling may open or close tiny gaps.
              (if (and shape (EL:Get 'segments shape) (not (EL:Get 'issues shape)))
                (progn
                  (setq started (EL:Tick) shape (EL:Put 'regions (append (EL:Get 'regions shape)
                    (EL:LogCall "DEVICE_REGIONS" context 'EL:ClosedRings (list (EL:Get 'segments shape)))) shape))
                  (EL:PerfCount "device-regions-build-ms" (EL:Elapsed started))))))
          (if (not shape)
            (progn
              (EL:PerfCount "device-contour-reads" 1)
              (setq started (EL:Tick))
              (setq shape (vl-catch-all-apply 'EL:DeviceContour (list entity)))
              (EL:PerfCount "device-instance-build-ms" (EL:Elapsed started))
              (if (vl-catch-all-error-p shape) (setq shape nil))
              (if (and (EL:Get 'segments shape) (not (EL:Get 'issues shape)))
                (progn
                  (setq started (EL:Tick) shape (EL:Put 'regions (append (EL:Get 'regions shape)
                    (EL:LogCall "DEVICE_REGIONS" context 'EL:ClosedRings (list (EL:Get 'segments shape)))) shape))
                  (EL:PerfCount "device-regions-build-ms" (EL:Elapsed started))))))
          ;; Sampled definition transforms remain forbidden. A fully built WCS
          ;; instance may nevertheless seed another instance of this exact pose.
          (if (and key (EL:ShapeGeometry shape) (not (EL:Get 'issues shape)) (not reusable)
              (EL:Get 'sampled-curves shape) (EL:Get 'pose-local-segments shape) (not (EL:Get 'curves shape)))
            (setq reusable 'pose))
          (if (EL:ShapeGeometry shape)
            (progn
              (setq started (EL:Tick) shape (EL:PrepareContactBlock (EL:Put 'contact-envelope (EL:Get 'bounds block)
                (EL:Put 'id id (EL:Put 'name (EL:Get 'name block) shape)))))
              (EL:PerfCount "device-contact-prepare-ms" (EL:Elapsed started))))
          (setq shape (EL:Put 'definition-key (cond ((equal reusable 'pose) pose-key)
              (reusable (list 'definition (cdr (assoc 2 data)))) (T (list 'instance id)))
            (EL:Put 'definition-geometry (if (equal reusable 'pose) source
              (EL:GeometryFacts (if reusable local-shape shape))) shape)))
          (if (and key reusable (EL:ShapeGeometry shape) (EL:Get 'contact-ready shape)
              (not (EL:Get 'issues shape)) (equal cache-context (EL:DeviceCacheContext)))
            (progn
              (EL:PerfCount "device-pose-builds" 1)
              (setq *EL:DeviceTemplateCache* (cons (list key origin shape) *EL:DeviceTemplateCache*))))))
      (setq shape (EL:Put 'id id (EL:Put 'name (EL:Get 'name block)
        (EL:Put 'cache-context cache-context
        (EL:Put 'instance-transform (list matrix (mapcar '(lambda (code) (assoc code data)) '(2 10 41 42 43 50 210))) shape)))))
      (if (or (not (EL:ShapeGeometry shape)) (EL:Get 'issues shape))
        (EL:LogEvent "DEVICE_CONTACT_GEOMETRY" (list id (EL:Get 'issues shape) 'no-bounds-fallback)))
      (setq *EL:DeviceContactCache* (cons (cons id shape) *EL:DeviceContactCache*))
      shape)))
(defun EL:DeviceContactTolerance (cfg / value)
  ;; Date: 2026-10-14. Drawing-unit XY tolerance; zero retains numerical epsilon.
  ;; Missing legacy values use 0.01 mm in this project's millimetre configuration.
  (setq value (EL:Get 'eps_device (EL:Get 'params cfg)))
  (if (EL:NonNegative value) (max (EL:GapEpsilon) value) 0.01))
(defun EL:StrictDeviceConfig (cfg)
  (EL:Put 'params (EL:Put 'eps_boundary (EL:DeviceContactTolerance cfg) (EL:Get 'params cfg)) cfg))
(defun EL:DevicePathBoundsHit (wire block cfg)
  (or (EL:PathBlockHit wire block (EL:Put 'params (EL:Put 'eps_boundary
      (max (EL:Get 'eps_boundary (EL:Get 'params cfg)) (EL:DeviceContactTolerance cfg))
      (EL:Get 'params cfg)) cfg))
    (and (EL:Get 'contact-strips wire)
      (EL:BoundsOverlap (EL:WireContactBounds wire) (EL:Get 'bounds block) (EL:DeviceContactTolerance cfg)))))
(defun EL:WideDevicePathHit (wire shape cfg / strip hit)
  (foreach strip (EL:Get 'contact-strips wire)
    (if (or (EL:ContourPathHit strip shape cfg)
        (vl-some '(lambda (seg) (EL:ContourPointHit (car (EL:ContactWorldSegment seg shape)) strip cfg))
          (EL:ContactRawSegments shape))
        (vl-some '(lambda (curve) (EL:ContourPointHit (EL:CurvePoint curve (nth 2 curve)) strip cfg))
          (EL:Get 'curves shape))) (setq hit T)))
  hit)
;; Date: 2026-10-22. Bounded fine-contact evidence for reported open-line lamp misses.
(defun EL:DeviceMissHead (items limit / out)
  (repeat limit (if items (setq out (cons (car items) out) items (cdr items))))
  (reverse out))
(defun EL:DeviceWireMissDetails (wire block shape cfg / count segments)
  (setq count (cond ((EL:Get "device-wire-miss-details" *EL:PerfMetrics*)) (T 0)))
  (if (and *EL:PerfActive* *EL:LogActive* (< count 8))
    (progn
      (EL:PerfCount "device-wire-miss-details" 1)
      (setq segments (EL:ContactRawSegments shape))
      (EL:LogEvent "DEVICE_WIRE_MISS_DETAILS" (list '(diagnostic-revision . "2026-10-22-line-arms1")
        (cons 'wire (EL:Get 'id wire)) (cons 'device (EL:Get 'id block))
        (cons 'device-name (EL:Get 'name block)) (cons 'device-bounds (EL:Get 'bounds block))
        '(phase . fine-contact-after-bounds) (cons 'device-tolerance (EL:DeviceContactTolerance cfg))
        (cons 'wire-segments (EL:DeviceMissHead (EL:Get 'segments wire) 8))
        (cons 'wire-truncated (> (length (EL:Get 'segments wire)) 8))
        (cons 'device-segment-count (length segments))
        (cons 'device-segments (mapcar '(lambda (seg) (EL:ContactWorldSegment seg shape))
          (EL:DeviceMissHead segments 32)))
        (cons 'device-segments-truncated (> (length segments) 32))
        (cons 'curve-count (length (EL:Get 'curves shape))) (cons 'geometry-issues (EL:Get 'issues shape)))))))
(defun EL:SimpleDevicePathHit (wire block cfg / shape hit)
  (cond ((equal (EL:Get 'role block) 'junction)
      (vl-some '(lambda (ep) (EL:SimpleDevicePointHit (EL:Get 'point ep) block cfg)) (EL:Get 'ends wire)))
    ((equal (EL:Get 'role block) 'panel) (EL:PathBlockHit wire block cfg))
    (T
    (and (EL:DevicePathBoundsHit wire block cfg)
      (progn
        (setq shape (EL:DeviceContactShape block)
          hit (EL:ContourPathHit wire shape (EL:StrictDeviceConfig cfg)))
        (if (and (not hit) (EL:WideDevicePathHit wire shape (EL:StrictDeviceConfig cfg)))
          (progn (setq hit T)
            (EL:LogEvent "DEVICE_WIRE_WIDTH_HIT" (list (cons 'wire (EL:Get 'id wire))
              (cons 'device (EL:Get 'id block)) (cons 'profiles (EL:Get 'width-profiles wire))))))
        (if (not hit)
          (progn
            (EL:LogEvent "DEVICE_WIRE_MISS" (list (cons 'wire (EL:Get 'id wire))
              (cons 'device (EL:Get 'id block)) (cons 'segments (EL:Get 'segments wire))
              (cons 'geometry-issues (EL:Get 'issues shape))))
            (EL:DeviceWireMissDetails wire block shape cfg)))
        hit)))))
(defun EL:SimpleDevicePointHit (point block cfg)
  (if (equal (EL:Get 'role block) 'panel) (EL:BlockPointHit point block cfg)
    (and (EL:BlockPointHit point block (EL:Put 'params (EL:Put 'eps_boundary
      (max (EL:Get 'eps_boundary (EL:Get 'params cfg)) (EL:DeviceContactTolerance cfg))
      (EL:Get 'params cfg)) cfg))
      (EL:ContourPointHit point (EL:DeviceContactShape block) (EL:StrictDeviceConfig cfg)))))
;; Date: 2026-10-13. Only real endpoints enter a registered junction.
(defun EL:JunctionTree (blocks / items block bounds)
  (foreach block blocks
    (if (and (equal (EL:Get 'role block) 'junction) (setq bounds (EL:Get 'bounds block)))
      (setq items (cons (list (cons 'key (EL:Get 'id block)) (cons 'block block) (cons 'bounds bounds)
        (cons 'point (EL:V* 0.5 (EL:V+ (car bounds) (cadr bounds))))) items))))
  (EL:SpatialTree items 0))
(defun EL:JunctionAtPoint (point tree cfg / item ids)
  (foreach item (EL:SpatialBoxQuery tree (list point point) (EL:DeviceContactTolerance cfg))
    (if (EL:SimpleDevicePointHit point (EL:Get 'block item) cfg) (setq ids (cons (EL:Get 'key item) ids)))) ids)
(defun EL:DevicesTouch (a b / sa sb seg edge hit segments candidates tol)
  (setq sa (EL:DeviceContactShape a) sb (EL:DeviceContactShape b)
    tol (if (numberp *EL:DeviceContactTolerance*) *EL:DeviceContactTolerance* (EL:DeviceContactTolerance nil)))
  (setq segments (EL:ContactRawSegments sa))
  (while (and segments (not hit))
    (setq seg (EL:ContactWorldSegment (car segments) sa) segments (cdr segments)
      candidates (EL:ContactSegmentsTolerance sb (EL:SegmentBounds (list seg)) tol))
    (while (and candidates (not hit))
      (setq edge (car candidates) candidates (cdr candidates))
      (if (EL:SegmentsTouchTolerance seg edge tol) (setq hit T))))
  (if (not hit)
    (setq hit (or
      (vl-some '(lambda (curve)
        (or (vl-some '(lambda (seg) (EL:CurveSegmentHit (EL:ContactWorldSegment seg sb) curve tol))
            (EL:ContactRawSegments sb))
          (vl-some '(lambda (other) (EL:CurvesTouchTolerance curve other tol)) (EL:Get 'curves sb)))) (EL:Get 'curves sa))
      (vl-some '(lambda (curve)
        (vl-some '(lambda (seg) (EL:CurveSegmentHit (EL:ContactWorldSegment seg sa) curve tol))
          (EL:ContactRawSegments sa))) (EL:Get 'curves sb)))))
  hit)
(defun EL:DeviceCandidateScope (snapshot cfg panel edges tree / block other wire ep endpoints limit rows)
  ;; Date: 2026-10-10. Conservative reachability only, never final connectivity.
  ;; Include every forward gap candidate, even ambiguous or blocked candidates.
  (foreach block (EL:Get 'blocks snapshot)
    (foreach other (EL:SpatialBoxQuery tree (EL:Get 'bounds block) (EL:GapEpsilon))
      ;; Date: 2026-10-13. Box overlap is symmetric; retain each pair once.
      (if (and (< (EL:Get 'id block) (EL:Get 'key other))
          (not (equal (EL:Get 'id block) panel)) (not (equal (EL:Get 'key other) panel)))
        (setq edges (cons (EL:Edge (EL:Get 'id block) (EL:Get 'key other)) edges)))))
  (foreach wire (EL:Get 'wires snapshot)
    (foreach other (EL:SpatialBoxQuery tree (EL:WireContactBounds wire)
        (EL:Get 'eps_boundary (EL:Get 'params cfg)))
      (if (EL:DevicePathBoundsHit wire (EL:Get 'block other) cfg)
        (setq edges (cons (EL:Edge (EL:Get 'id wire) (EL:Get 'key other)) edges)))))
  (setq endpoints (EL:SpatialTree (vl-remove-if-not 'EL:GapEligible (EL:Get 'ends snapshot)) 0)
    limit (EL:Get 'Dmax (EL:Get 'params cfg)))
  (foreach ep (EL:Get 'ends snapshot)
    (if (EL:GapEligible ep)
      (foreach other (EL:SpatialRayQuery endpoints (EL:Get 'point ep) (EL:Get 'direction ep) limit)
        (if (not (equal (EL:Get 'wire ep) (EL:Get 'wire other)))
          (setq edges (cons (EL:Edge (EL:Get 'wire ep) (EL:Get 'wire other)) edges))))))
  (setq rows (EL:Component panel (EL:Unique edges)))
  (EL:LogEvent "DEVICE_CANDIDATE_SCOPE" (list (cons 'objects (length rows))
    (cons 'blocks (length (EL:Get 'blocks snapshot)))))
  rows)
;; Date: 2026-10-11. A memo is a candidate only, never proof of unchanged source.
;; Every call receives a newly collected snapshot. Re-read every tested geometry
;; dependency; no prior definition/shape cache crosses this check.
(setq *EL:NetworkMemo* nil)
(defun EL:NetworkGeometryCurrent (contacts snapshot / row block shape good)
  ;; Date: 2026-10-13. Re-read all tested instances, then compare the exact template pool.
  (setq good (and (EL:OnlyKeys contacts '(version templates instances))
    (equal (EL:Get 'version contacts) 3) (assoc 'templates contacts) (assoc 'instances contacts)))
  (foreach row (EL:Get 'instances contacts)
    (if good
      (progn
        (setq block (EL:By 'id (car row) (EL:Get 'blocks snapshot)))
        (if block
          (progn
            (EL:PerfCount "network-geometry-checks" 1)
            (setq shape (EL:DeviceContactShape block)
              good (and (EL:ShapeGeometry shape) (not (EL:Get 'issues shape)))))
          (setq good nil)))))
  (and good (equal contacts (EL:DeviceContactEvidence *EL:DeviceContactCache*))))
(defun EL:NetworkRoleCodeLess (a b)
  ;; Date: 2026-10-21. Compare numeric character codes, including full prefixes.
  (while (and a b (= (car a) (car b))) (setq a (cdr a) b (cdr b)))
  (and b (or (not a) (< (car a) (car b)))))
(defun EL:NetworkRolesOrdered (blocks roles / tail ids sorted previous ordered block id)
  ;; Date: 2026-10-21. A positional restore is safe only for unique, aligned IDs.
  ;; Sorting bounded handle-code lists avoids a second quadratic MEMBER scan.
  (setq tail roles ordered (= (length blocks) (length roles)))
  (foreach block blocks
    (if ordered
      (progn
        (setq id (EL:Get 'id block))
        (if (and (equal (type id) 'STR) (equal id (car (car tail))))
          (setq ids (cons (vl-string->list id) ids) tail (cdr tail))
          (setq ordered nil)))))
  (if ordered
    (progn
      (setq sorted (vl-sort ids 'EL:NetworkRoleCodeLess)
        ordered (= (length ids) (length sorted)))
      ;; Native VL-SORT may remove duplicates; host adapters may retain them.
      ;; The length and adjacent checks reject duplicates under either behavior.
      (while (and ordered sorted)
        (if (and previous (equal (car previous) (car sorted))) (setq ordered nil))
        (setq previous sorted sorted (cdr sorted))))) ordered)
(defun EL:NetworkRestoreRoles (blocks roles / ordered tail rows block role)
  ;; Date: 2026-10-21. Keep first-ASSOC semantics for every noncanonical table.
  (setq ordered (EL:NetworkRolesOrdered blocks roles) tail roles)
  (EL:PerfCount "network-role-blocks" (length blocks))
  (EL:PerfCount (if ordered "network-role-ordered-batches" "network-role-fallback-batches") 1)
  (foreach block blocks
    (setq role (if ordered (cdr (car tail)) (EL:Get (EL:Get 'id block) roles)))
    (if ordered (setq tail (cdr tail)))
    (setq block (if role (EL:Put 'role (cdr role) block)
      (vl-remove-if '(lambda (pair) (equal (car pair) 'role)) block)))
    (setq rows (cons block rows))) (reverse rows))
(defun EL:NetworkProofInput (baseline proof / rows key blocks)
  ;; Date: 2026-10-13. Restore only the fields changed by network construction.
  ;; Everything else references the existing source-signature snapshot.
  (foreach key (EL:Get 'input-keys proof)
    (cond
      ((equal key 'ends) (setq rows (cons (cons key (EL:Get 'input-ends proof)) rows)))
      ((equal key 'blocks)
        (setq blocks (EL:PerfCall "NETWORK_ROLE_RESTORE" 'EL:NetworkRestoreRoles
          (list (EL:Get 'blocks baseline) (EL:Get 'input-roles proof))))
        (setq rows (cons (cons key blocks) rows)))
      (T (setq rows (cons (assoc key baseline) rows))))) (reverse rows))
(defun EL:NetworkProofMake (input output cfg panel contacts / proof roles block restored)
  ;; Date: 2026-10-21. Batch timings separate conversion, evidence and exact check.
  (setq input (EL:PerfCall "NETWORK_PROOF_STABLE_INPUT" 'EL:StableSnapshot (list input))
    output (EL:PerfCall "NETWORK_PROOF_STABLE_OUTPUT" 'EL:StableSnapshot (list output)))
  (foreach block (EL:Get 'blocks input)
    (setq roles (cons (cons (EL:Get 'id block) (assoc 'role block)) roles)))
  (setq proof (list '(version . 4) (cons 'panel panel)
    (cons 'config (EL:StableData (vl-remove-if '(lambda (row) (equal (car row) 'template)) cfg)))
    (cons 'input-keys (mapcar 'car input)) (cons 'input-ends (EL:Get 'ends input))
    (cons 'input-roles (reverse roles))
    (cons 'contacts (EL:PerfCall "NETWORK_PROOF_CONTACTS" 'EL:DeviceContactEvidence (list contacts)))))
  ;; Any future builder mutation outside the known patch disables reuse safely.
  (setq restored (EL:NetworkProofInput output proof))
  (if (EL:PerfCall "NETWORK_PROOF_COMPARE" 'equal (list input restored)) proof))
(defun EL:SimpleNetwork (snapshot cfg panel / saved key epoch result reused proof *EL:DeviceContactCache* *EL:DeviceTemplateCache* *EL:DeviceTemplateEnabled*)
  (setq *EL:DeviceTemplateEnabled* T epoch *EL:FreshEpoch*
    ;; Date: 2026-10-13. Dialog template selection changes drawing output only;
    ;; preserve every other config field, including unknown future fields.
    key (list (namedobjdict) (vl-remove-if '(lambda (row) (equal (car row) 'template)) cfg) panel snapshot)
    saved (if (and *EL:PerfActive* (not *EL:NetworkReuseDisabled*)) *EL:NetworkMemo*)
    *EL:NetworkMemo* nil)
  ;; Snapshot and configuration comparison is exact, including all candidate
  ;; wires/blocks, panel/trunk geometry and issues. Different input rebuilds.
  (if (and saved (equal key (car saved))
      (EL:PerfCall "NETWORK_VERIFY_GEOMETRY" 'EL:NetworkGeometryCurrent
        (list (caddr saved) snapshot)) (equal epoch *EL:FreshEpoch*))
    (progn (setq result (cadr saved) reused T)
      (EL:PerfCount "network-verified-reuses" 1)))
  (if (not reused)
    (progn
      ;; A failed comparison may have populated a partial cache in another
      ;; order. Rebuild with the original fresh-pass geometry semantics.
      (setq *EL:DeviceContactCache* nil *EL:DeviceTemplateCache* nil)
      (EL:PerfCount "network-build-calls" 1)
      (setq result (EL:PerfCall "NETWORK_BUILD" 'EL:SimpleNetworkBuild (list snapshot cfg panel)))))
  (if (not (and (equal epoch *EL:FreshEpoch*) (equal (car key) (namedobjdict))))
    (progn (setq *EL:NetworkMemo* nil)
      (EL:Require nil "SOURCE_CHANGED：建网复核期间发生写入、交互或切图，请重新统计。")))
  ;; The compact proof is a candidate; current inputs/shapes are read again.
  (if (and result (not (EL:Get 'issues snapshot))
      (vl-every '(lambda (row) (and (EL:ShapeGeometry (cdr row))
        (not (EL:Get 'issues (cdr row))))) *EL:DeviceContactCache*)
      (setq proof (EL:PerfCall "NETWORK_PROOF_PREPARE" 'EL:NetworkProofMake
        (list snapshot (EL:Get 'snapshot result) cfg panel *EL:DeviceContactCache*))))
    (setq result (EL:Put 'snapshot (EL:Put 'network-proof proof (EL:Get 'snapshot result)) result)))
  (if (and result *EL:PerfActive* (not *EL:NetworkReuseDisabled*)
      (equal epoch *EL:FreshEpoch*) (not (EL:Get 'issues snapshot))
      (vl-every '(lambda (row) (and (EL:ShapeGeometry (cdr row))
        (not (EL:Get 'issues (cdr row))))) *EL:DeviceContactCache*))
    (setq *EL:NetworkMemo* (list key result (EL:DeviceContactEvidence *EL:DeviceContactCache*)))
    (setq *EL:NetworkMemo* nil))
  ;; Date: 2026-10-21. Share successful definitions, poses and instances with
  ;; the next split of this synchronous recognition. Never persist this cache.
  (if *EL:RecognitionPass*
    (setq *EL:RecognitionContacts* (list result (namedobjdict) *EL:FreshEpoch*
      *EL:DeviceTemplateCache* *EL:DeviceContactCache*)))
  result)
(defun EL:SimpleGapSnapshot (snapshot)
  ;; Date: 2026-10-13. Virtual continuation joins only the two free wire ends.
  ;; Intermediate devices are not physical contacts or obstacles. Retain the
  ;; selected panel and real wires as blockers; occupancy is already verified.
  (EL:Put 'blocks (vl-remove-if-not '(lambda (block) (equal (EL:Get 'role block) 'panel))
    (EL:Get 'blocks snapshot)) snapshot))
 ;; Date: 2026-10-13. Only exact neighbours reached from the picked roots enter the queue.
(defun EL:WalkLink (a b / edge)
  (if (not (equal a b))
    (progn
      (setq edge (EL:Edge a b) *EL:WalkEdges* (cons edge *EL:WalkEdges*))
      (if (and (not (equal b *EL:WalkPanel*)) (not (member b *EL:WalkSeen*))
          (not (member b *EL:WalkQueue*)))
        (setq *EL:WalkQueue* (cons b *EL:WalkQueue*))))))
(defun EL:WalkEnd (ep / saved point junctions occupied item wire direct state)
  (if (setq saved (assoc (EL:Get 'key ep) *EL:WalkEnds*)) (cdr saved)
    (progn
      (if *EL:RootScopeActive*
        (EL:RootScopeResolve (cdr (assoc (EL:Get 'wire ep) *EL:WalkWireRecords*))))
      (setq point (EL:Get 'point ep)
        occupied (or (EL:StartBoundaryPoint point *EL:WalkSnapshot* *EL:WalkConfig*)
          (EL:TrunkPoint point (EL:Get 'trunk-segments *EL:WalkSnapshot*))))
      (if (not occupied) (setq junctions (EL:JunctionAtPoint point *EL:WalkJunctionTree* *EL:WalkConfig*)))
      (setq occupied (or occupied junctions))
      (if (not occupied)
        (foreach item (EL:SpatialBoxQuery *EL:WalkWireTree* (list point point) *EL:WalkTouch*)
          (setq wire (EL:RootScopeResolve (EL:Get 'wire item)))
          (if (and (not (equal (EL:Get 'wire ep) (EL:Get 'id wire)))
              (EL:Touches point (EL:Get 'segments wire) *EL:WalkTouch* (EL:GapEpsilon)))
            (setq direct (cons (EL:Get 'id wire) direct)))))
      (setq state (EL:SimpleEndState (EL:Put 'occupied (or occupied direct) ep)
        *EL:WalkBlockTree* *EL:WalkConfig*)
        state (EL:Put 'junctions junctions (EL:Put 'direct-wires direct state))
        *EL:WalkEnds* (cons (cons (EL:Get 'key ep) state) *EL:WalkEnds*))
      state)))
(defun EL:WalkGapRow (ep / saved a b item accepted rejected rec row)
  (if (setq saved (assoc (EL:Get 'key ep) *EL:WalkGapRows*)) (cdr saved)
    (progn
      (setq a (EL:WalkEnd ep))
      (if (EL:GapEligible a)
        (foreach item (EL:SpatialRayQuery *EL:WalkEndTree* (EL:Get 'point a)
            (EL:Get 'direction a) (EL:Get 'Dmax (EL:Get 'params *EL:WalkConfig*)))
          (if (and (not (equal (EL:Get 'key a) (EL:Get 'key item))) (EL:GapEligible item))
            (progn
              ;; Candidate endpoint occupancy is a dependency of mutual uniqueness.
              (setq b (EL:WalkEnd item))
              (if (EL:GapEligible b)
                (progn
                  (setq rec (EL:ValidateGapPair a b *EL:WalkGapSnapshot* *EL:WalkConfig*))
                  (if (EL:Get 'accepted rec) (setq accepted (cons rec accepted))
                    (setq rejected (cons rec rejected)))))))))
      (setq row (list (cons 'key (EL:Get 'key a))
        (cons 'candidates (vl-sort accepted 'EL:CandidateLess))
        (cons 'rejected (vl-sort rejected '(lambda (a b)
          (< (EL:Signature (EL:Get 'target a)) (EL:Signature (EL:Get 'target b)))))))
        *EL:WalkGapRows* (cons (cons (EL:Get 'key a) row) *EL:WalkGapRows*))
      row)))
(defun EL:WalkGap (ep / row candidate other reverse-row)
  (setq row (EL:WalkGapRow ep))
  (if (= (length (EL:Get 'candidates row)) 1)
    (progn
      (setq candidate (car (EL:Get 'candidates row))
        other (cdr (assoc (EL:Get 'target candidate) *EL:WalkEndRecords*))
        reverse-row (EL:WalkGapRow other))
      (if (and (= (length (EL:Get 'candidates reverse-row)) 1)
          (equal (EL:Get 'target (car (EL:Get 'candidates reverse-row))) (EL:Get 'key ep)))
        (EL:WalkLink (EL:Get 'wire ep) (EL:Get 'wire other))))))
(defun EL:WalkDevicePathHit (wire block / key saved hit)
  ;; Date: 2026-10-15. Both directions of the walk ask the same predicate.
  ;; Cache misses as well as hits, scoped to these immutable fresh records.
  (setq key (list (EL:Get 'id wire) (EL:Get 'id block)))
  (if (setq saved (assoc key *EL:WalkContactHits*)) (cdr saved)
    (progn
      (setq hit (EL:SimpleDevicePathHit wire block *EL:WalkConfig*)
        *EL:WalkContactHits* (cons (cons key hit) *EL:WalkContactHits*)) hit)))
(defun EL:WalkPathHit (wire block)
  (if (equal (EL:Get 'role block) 'junction)
    (vl-some '(lambda (ep) (and
      (not (EL:StartBoundaryPoint (EL:Get 'point ep) *EL:WalkSnapshot* *EL:WalkConfig*))
      (not (EL:TrunkPoint (EL:Get 'point ep) (EL:Get 'trunk-segments *EL:WalkSnapshot*)))
      (EL:SimpleDevicePointHit (EL:Get 'point ep) block *EL:WalkConfig*))) (EL:Get 'ends wire))
    (EL:WalkDevicePathHit wire block)))
(defun EL:WalkWire (wire / id ep state other item block point)
  (setq id (EL:Get 'id wire))
  (foreach ep (EL:Get 'ends wire)
    (setq state (EL:WalkEnd ep))
    (foreach other (EL:Get 'junctions state) (EL:WalkLink id other))
    (foreach other (EL:Get 'direct-wires state) (EL:WalkLink id other)))
  ;; Reverse endpoint queries retain T branches when the reached wire is the trunk.
  ;; Two crossing interiors have no endpoint and therefore never enter the queue.
  (foreach ep (EL:SpatialBoxQuery *EL:WalkEndTree* (EL:WireContactBounds wire) *EL:WalkTouch*)
    (setq point (EL:Get 'point ep))
    (if (and (not (equal id (EL:Get 'wire ep)))
        (EL:Touches point (EL:Get 'segments wire) *EL:WalkTouch* (EL:GapEpsilon)))
      (progn
        (setq state (EL:WalkEnd ep))
        (if (member id (EL:Get 'direct-wires state)) (EL:WalkLink id (EL:Get 'wire ep))))))
  (foreach item (EL:SpatialBoxQuery *EL:WalkBlockTree* (EL:WireContactBounds wire)
      (max *EL:WalkTouch* *EL:DeviceContactTolerance*
        (EL:Get 'eps_boundary (EL:Get 'params *EL:WalkConfig*))))
    (setq block (EL:Get 'block item))
    (if (and (not (equal (EL:Get 'id block) *EL:WalkPanel*))
        (EL:WalkPathHit wire block))
      (EL:WalkLink id (EL:Get 'id block))))
  (foreach ep (EL:Get 'ends wire) (EL:WalkGap ep)))
(defun EL:WalkBlock (block / id item other wire ep)
  (setq id (EL:Get 'id block))
  (if (equal (EL:Get 'role block) 'junction)
    ;; A registered node accepts real endpoints only, never a crossing interior.
    (foreach ep (EL:SpatialBoxQuery *EL:WalkEndTree* (EL:Get 'bounds block) (EL:GapEpsilon))
      (if (member id (EL:Get 'junctions (EL:WalkEnd ep)))
        (EL:WalkLink id (EL:Get 'wire ep))))
    (progn
      (foreach item (EL:SpatialBoxQuery *EL:WalkBlockTree* (EL:Get 'bounds block) *EL:DeviceContactTolerance*)
        (setq other (EL:Get 'block item))
        (if (and (equal (EL:Get 'role other) 'device) (not (equal id (EL:Get 'id other)))
            (EL:DevicesTouch block other)) (EL:WalkLink id (EL:Get 'id other))))
      (foreach item (EL:SpatialBoxQuery *EL:WalkWireTree* (EL:Get 'bounds block)
          (max *EL:WalkTouch* *EL:DeviceContactTolerance*))
        (setq wire (EL:RootScopeResolve (EL:Get 'wire item)))
        (if (EL:WalkDevicePathHit wire block)
          (EL:WalkLink id (EL:Get 'id wire)))))))
(defun EL:NetworkEdges (edges / row previous rows)
  ;; Date: 2026-10-13. Sort small handle pairs, then deduplicate adjacent edges.
  (foreach row (vl-sort edges '(lambda (a b)
      (if (equal (car a) (car b)) (< (cadr a) (cadr b)) (< (car a) (car b)))))
    (if (not (equal row previous)) (setq rows (cons row rows) previous row)))
  (reverse rows))
(defun EL:SimpleNetworkBuild (snapshot cfg panel / wires blocks block wire bounds items ends ep row pairs perf id indexperf
    *EL:WalkPanel* *EL:WalkConfig* *EL:WalkSnapshot* *EL:WalkTouch*
    *EL:WalkWireTree* *EL:WalkBlockTree* *EL:WalkEndTree* *EL:WalkJunctionTree*
    *EL:WalkWireRecords* *EL:WalkBlockRecords* *EL:WalkEndRecords*
    *EL:WalkQueue* *EL:WalkSeen* *EL:WalkEdges* *EL:WalkEnds* *EL:WalkGapRows* *EL:WalkContactHits*
    *EL:WalkGapSnapshot* *EL:GapPathIndex* *EL:GapIndexReady* *EL:DeviceContactTolerance*)
  (setq *EL:DeviceTemplateEnabled* T *EL:DeviceContactTolerance* (EL:DeviceContactTolerance cfg)
    wires (EL:Get 'wires snapshot)
    *EL:WalkPanel* panel *EL:WalkConfig* cfg
    *EL:WalkTouch* (EL:Get 'eps_touch (EL:Get 'params cfg))
    perf (EL:PerfBegin "NETWORK_CANDIDATE_SCOPE"))
  ;; Date: 2026-10-21. Split existing batches while retaining all construction order.
  (setq indexperf (EL:PerfBegin "NETWORK_ROLE_PREPARE"))
  (foreach block (EL:Get 'blocks snapshot)
    (setq block (EL:Put 'role (EL:FixedBlockRole block panel cfg) block)
      blocks (cons block blocks) *EL:WalkBlockRecords* (cons (cons (EL:Get 'id block) block) *EL:WalkBlockRecords*)))
  (setq blocks (reverse blocks) snapshot (EL:Put 'blocks blocks snapshot) *EL:WalkSnapshot* snapshot)
  (EL:PerfEnd indexperf 'returned)
  (setq indexperf (EL:PerfBegin "NETWORK_WIRE_INDEX"))
  (foreach wire wires
    (setq *EL:WalkWireRecords* (cons (cons (EL:Get 'id wire) wire) *EL:WalkWireRecords*)
      bounds (EL:WireContactBounds wire))
    (if bounds (setq items (cons (list (cons 'key (EL:Get 'id wire)) (cons 'wire wire) (cons 'bounds bounds)
      (cons 'point (EL:V* 0.5 (EL:V+ (car bounds) (cadr bounds))))) items))))
  (setq *EL:WalkWireTree* (EL:SpatialTree items 0) items nil)
  (EL:PerfEnd indexperf 'returned)
  (setq indexperf (EL:PerfBegin "NETWORK_BLOCK_INDEX"))
  (foreach block blocks
    (if (setq bounds (EL:Get 'bounds block))
      (setq items (cons (list (cons 'key (EL:Get 'id block)) (cons 'block block) (cons 'bounds bounds)
        (cons 'point (EL:V* 0.5 (EL:V+ (car bounds) (cadr bounds))))) items))))
  (setq *EL:WalkBlockTree* (EL:SpatialTree items 0))
  (EL:PerfEnd indexperf 'returned)
  (setq indexperf (EL:PerfBegin "NETWORK_JUNCTION_INDEX")
    *EL:WalkJunctionTree* (EL:JunctionTree blocks))
  (EL:PerfEnd indexperf 'returned)
  (setq indexperf (EL:PerfBegin "NETWORK_END_INDEX")
    *EL:WalkEndTree* (EL:SpatialTree (mapcar '(lambda (ep)
      (EL:Put 'bounds (list (EL:Get 'point ep) (EL:Get 'point ep)) ep)) (EL:Get 'ends snapshot)) 0))
  (EL:PerfEnd indexperf 'returned)
  (setq indexperf (EL:PerfBegin "NETWORK_GAP_INDEX")
    *EL:WalkGapSnapshot* (EL:SimpleGapSnapshot snapshot)
    *EL:GapPathIndex* (EL:GapPathIndex *EL:WalkGapSnapshot*) *EL:GapIndexReady* T)
  (EL:PerfEnd indexperf 'returned)
  (setq indexperf (EL:PerfBegin "NETWORK_ROOT_LINKS"))
  (foreach ep (EL:Get 'ends snapshot)
    (setq *EL:WalkEndRecords* (cons (cons (EL:Get 'key ep) ep) *EL:WalkEndRecords*)))
  (foreach wire wires
    (if (cond ((EL:Get 'circuit-starts snapshot) (EL:By 'wire (EL:Get 'id wire) (EL:Get 'circuit-starts snapshot)))
        ((EL:Get 'trunk-segments snapshot) (member (EL:Get 'id wire) (EL:Get 'trunk-roots snapshot)))
        (T (EL:PathBlockHit wire (cdr (assoc panel *EL:WalkBlockRecords*)) cfg)))
      (EL:WalkLink panel (EL:Get 'id wire))))
  (EL:PerfEnd indexperf 'returned)
  (EL:PerfEnd perf 'returned)
  (setq perf (EL:PerfBegin "NETWORK_REACHABLE_TRACE"))
  (while *EL:WalkQueue*
    (setq id (car *EL:WalkQueue*) *EL:WalkQueue* (cdr *EL:WalkQueue*))
    (if (not (member id *EL:WalkSeen*))
      (progn
        (setq *EL:WalkSeen* (cons id *EL:WalkSeen*))
        (if (setq wire (cdr (assoc id *EL:WalkWireRecords*))) (EL:WalkWire wire)
          (if (setq block (cdr (assoc id *EL:WalkBlockRecords*))) (EL:WalkBlock block))))))
  (EL:LogEvent "DEVICE_CANDIDATE_SCOPE" (list (cons 'objects (length *EL:WalkSeen*))
    (cons 'blocks (length blocks)) (cons 'policy 'exact-root-walk)))
  (EL:PerfEnd perf 'returned)
  (setq perf (EL:PerfBegin "NETWORK_GAPS"))
  (foreach ep (EL:Get 'ends snapshot)
    (setq row (assoc (EL:Get 'key ep) *EL:WalkEnds*) ends (cons (if row (cdr row) ep) ends)))
  (setq snapshot (EL:Put 'ends (reverse ends) snapshot)
    pairs (EL:BuildMutualPairs (mapcar 'cdr (reverse *EL:WalkGapRows*)) snapshot cfg))
  (EL:SimpleGapLog (EL:Put 'ends (vl-remove-if-not '(lambda (ep) (member (EL:Get 'wire ep) *EL:WalkSeen*))
    (EL:Get 'ends snapshot)) snapshot) cfg (mapcar 'cdr *EL:WalkGapRows*) pairs)
  (EL:PerfEnd perf 'returned)
  (setq perf (EL:PerfBegin "NETWORK_CONTACT_NODES")
    *EL:WalkEdges* (EL:NormalizeContactEdges (EL:Put 'gap-pairs (EL:Get 'pairs pairs) snapshot)
      (EL:NetworkEdges *EL:WalkEdges*) cfg))
  (EL:PerfEnd perf 'returned)
  (setq perf (EL:PerfBegin "NETWORK_SIGNATURE")
    snapshot (EL:Put 'device-contact-signature (EL:DeviceContactEvidence *EL:DeviceContactCache*) snapshot))
  (EL:PerfEnd perf 'returned)
  (list (cons 'edges *EL:WalkEdges*) (cons 'snapshot snapshot) (cons 'panel panel)
    (cons 'devices (vl-remove-if-not '(lambda (b) (and (equal (EL:Get 'role b) 'device)
      (member (EL:Get 'id b) *EL:WalkSeen*))) blocks))
    (cons 'wire-ids (vl-remove-if-not '(lambda (id) (member id *EL:WalkSeen*)) (mapcar '(lambda (w) (EL:Get 'id w)) wires)))
    (cons 'gap-pairs (vl-remove-if-not '(lambda (p) (member (car (EL:Get 'a p)) *EL:WalkSeen*)) (EL:Get 'pairs pairs)))
    (cons 'gap-issues (EL:SimpleBlockingGapIssues (vl-remove-if-not '(lambda (issue)
      (member (EL:Get 'object issue) *EL:WalkSeen*)) (EL:Get 'issues pairs))))))

(defun EL:SimplePowersValid (data / ok seen row)
  (setq ok (and (EL:OnlyKeys data '(version powers)) (equal (EL:Get 'version data) 1) (listp (EL:Get 'powers data))))
  (foreach row (EL:Get 'powers data)
    (if (or (not (equal (type (car row)) 'STR)) (equal (car row) "")
            (member (car row) seen) (not (equal (type (cdr row)) 'INT))
            (and (numberp (cdr row)) (< (cdr row) 0))) (setq ok nil))
    (setq seen (cons (car row) seen))) ok)
(defun EL:SimpleLoadPowers (/ path raw checked)
  (setq path (strcat *EL:Root* "config/block-powers.eld"))
  (if (not (findfile path)) (list (cons 'version 1) (cons 'powers nil))
    (progn (setq raw (EL:ReadData path) checked (vl-catch-all-apply 'EL:SimplePowersValid (list raw)))
      (if (and checked (not (vl-catch-all-error-p checked))) raw
        (progn (princ "\n图块功率文件无法读取，原文件已保留：config/block-powers.eld") nil)))))
(defun EL:SimpleRows (devices powers / rows block key row)
  (foreach block devices
    (setq key (strcase (EL:Get 'name block)) row (EL:By 'key key rows))
    (if row
      (setq rows (subst (EL:Put 'ids (cons (EL:Get 'id block) (EL:Get 'ids row))
        (EL:Put 'count (1+ (EL:Get 'count row)) row)) row rows))
      (setq rows (cons (list (cons 'key key) (cons 'name (EL:Get 'name block)) (cons 'count 1)
        (cons 'ids (list (EL:Get 'id block))) (cons 'watts (EL:Get key powers))) rows))))
  (if rows (vl-sort rows '(lambda (a b) (< (EL:Get 'key a) (EL:Get 'key b))))))
(defun EL:SimpleSavePowers (rows / data powers row)
  ;; Reload before merge; preserve types not present in the current system.
  (if (setq data (EL:SimpleLoadPowers))
    (progn (setq powers (EL:Get 'powers data))
      (foreach row rows (setq powers (EL:Put (EL:Get 'key row) (EL:Get 'watts row) powers)))
      (EL:WriteData (strcat *EL:Root* "config/block-powers.eld") (list (cons 'version 1) (cons 'powers powers))))))
(defun EL:SimpleTotal (rows / total complete row)
  (setq total 0.0 complete T)
  (foreach row rows
    (if (numberp (EL:Get 'watts row)) (setq total (+ total (* 1.0 (EL:Get 'count row) (EL:Get 'watts row))))
      (setq complete nil)))
  (if complete total))
(defun EL:SimpleStoreField (/ row value watts)
  (setq row (nth *EL:SimpleIndex* *EL:SimpleRows*) value (get_tile "s_edit") watts (EL:ParseWatts value))
  (if (or (equal value "") (numberp watts))
    (progn (setq *EL:SimpleRows* (subst (EL:Put 'watts watts row) row *EL:SimpleRows*)) T)
    (progn (set_tile "s_status" "功率请输入非负整数 W。") nil)))
(defun EL:SimpleFill (/ row total)
  (start_list "s_header") (add_list "设备图块\t数量\t单个功率（W）") (end_list)
  (start_list "s_names")
  (foreach row *EL:SimpleRows*
    (add_list (strcat (EL:Get 'name row) "\t" (itoa (EL:Get 'count row)) "\t"
      (if (numberp (EL:Get 'watts row)) (itoa (EL:Get 'watts row)) "待填写"))))
  (end_list) (set_tile "s_names" (itoa *EL:SimpleIndex*))
  (setq row (nth *EL:SimpleIndex* *EL:SimpleRows*) total (EL:SimpleTotal *EL:SimpleRows*))
  (set_tile "s_selected" (strcat "当前设备：" (EL:Get 'name row) "  数量：" (itoa (EL:Get 'count row))))
  (set_tile "s_edit" (if (numberp (EL:Get 'watts row)) (itoa (EL:Get 'watts row)) ""))
  (set_tile "s_status" (if total (strcat "设备总功率：" (rtos total 2 0) " W。保存后下次自动带入。") "请填写各类设备的单个功率，保存后下次自动带入。")))
(defun EL:SimpleSelect (value)
  (if (EL:SimpleStoreField)
    (progn (setq *EL:SimpleIndex* (atoi value)) (done_dialog 2))
    (set_tile "s_names" (itoa *EL:SimpleIndex*))))
(defun EL:SimpleAccept ()
  (if (EL:SimpleStoreField)
    (if (EL:SimpleTotal *EL:SimpleRows*) (done_dialog 1)
      (set_tile "s_status" "还有功率未填写，请填完后保存。"))))
(defun EL:SimpleZoom (lo hi / pad)
  (setq pad (* 0.12 (max 1.0 (- (car hi) (car lo)) (- (cadr hi) (cadr lo)))))
  (vla-ZoomWindow (vlax-get-acad-object)
    (vlax-3d-point (EL:V- lo (list pad pad 0.0)))
    (vlax-3d-point (EL:V+ hi (list pad pad 0.0)))))
(defun EL:SimpleLocate (result row / id block bounds seg pad lo hi)
  (EL:ClearGapPreview) (EL:ClearPickHighlights)
  (foreach id (EL:Get 'ids row)
    (setq bounds (EL:Get 'bounds (EL:By 'id id (EL:Get 'devices result))))
    (if bounds (setq lo (if lo (mapcar 'min lo (car bounds)) (car bounds))
                    hi (if hi (mapcar 'max hi (cadr bounds)) (cadr bounds)))))
  (if lo (vl-catch-all-apply 'EL:SimpleZoom (list lo hi)))
  (setq pad (/ (getvar "VIEWSIZE") 150.0))
  (foreach id (EL:Get 'ids row)
    (EL:LocateID id)
    (setq block (EL:By 'id id (EL:Get 'devices result)) bounds (EL:ExpandedBlockBounds (EL:Get 'bounds block) pad))
    (foreach seg (EL:BoundsSegments bounds) (EL:DrawTransient (car seg) (cadr seg) 2)))
  (princ (strcat "\n黄色框：" (EL:Get 'name row) "，共 " (itoa (EL:Get 'count row)) " 个。")))
(defun EL:SimpleDialog (result rows / dialog status *EL:SimpleRows* *EL:SimpleIndex*)
  (setq *EL:SimpleRows* rows *EL:SimpleIndex* 0 status 2
        dialog (load_dialog (strcat *EL:Root* "ui/power.dcl")) *EL:DialogID* dialog)
  (while (and (> dialog 0) (= status 2))
    (if (new_dialog "el_devices" dialog)
      (progn
        (EL:SimpleFill)
        (EL:MonitorActionTile "s_names" "(EL:SimpleSelect $value)")
        (EL:MonitorActionTile "s_locate" "(if (EL:SimpleStoreField) (done_dialog 2))")
        (EL:MonitorActionTile "s_edit" "(if (EL:SimpleStoreField) (EL:SimpleFill))")
        (EL:MonitorActionTile "accept" "(EL:SimpleAccept)")
        (EL:MonitorActionTile "cancel" "(done_dialog 0)")
        (setq status (start_dialog))
        (if (= status 2)
          (progn (EL:SimpleLocate result (nth *EL:SimpleIndex* *EL:SimpleRows*))
            (getstring "\n按 Enter 返回设备功率表：") (EL:ClearGapPreview) (EL:ClearPickHighlights))))
      (setq status 0)))
  (if (> dialog 0) (unload_dialog dialog)) (setq *EL:DialogID* nil)
  (EL:ClearPickHighlights)
  (if (= status 1) *EL:SimpleRows*))
(defun EL:SimpleEdit (result / *error* data rows edited)
  (defun *error* (msg)
    (EL:LogFailure msg) (vl-catch-all-apply 'EL:ClearGapPreview nil)
    (vl-catch-all-apply 'EL:ClearPickHighlights nil) (vl-catch-all-apply 'EL:ReleasePowerUI nil)
    (if msg (princ (strcat "\n设备表已取消，未保存修改：" msg))) (princ))
  (if (and (EL:EnsureRoot) (setq data (EL:SimpleLoadPowers)))
    (progn
      (setq rows (EL:SimpleRows (EL:Get 'devices result) (EL:Get 'powers data)))
      (if (setq edited (EL:SimpleDialog result rows))
        (if (EL:SimpleSavePowers edited)
          (progn (setq *EL:DeviceResult* (EL:Put 'rows edited (EL:Put 'total-watts (EL:SimpleTotal edited) result)))
            (princ (strcat "\n已保存图块功率。设备合计 " (rtos (EL:SimpleTotal edited) 2 0) " W。")))
          (princ "\n功率未保存，请检查 config 目录写入权限；原文件保留。")))))
  (princ))
(defun EL:SimpleStat (/ *error* cfg panel pd snapshot result *EL:SimpleEntity*)
  (defun *error* (msg)
    (EL:LogEvent "SIMPLE_ENTITY" *EL:SimpleEntity*)
    (EL:LogFailure msg) (vl-catch-all-apply 'EL:ClearGapPreview nil)
    (vl-catch-all-apply 'EL:ClearPickHighlights nil) (vl-catch-all-apply 'EL:ReleasePowerUI nil)
    (setq *EL:DeviceResult* nil) (if msg (princ (strcat "\n设备统计已停止：" msg))) (princ))
  (setq *EL:Result* nil *EL:DeviceResult* nil)
  (EL:LogStart) (EL:ClearPickHighlights)
  (if (and (EL:EnsureRoot)
           (setq panel (EL:PickModel 'panel "\n拾取配电箱："))
           (setq cfg (EL:PanelWireConfig (car panel)
             (EL:Put 'params (EL:GapParams (EL:SuggestedParams)) (EL:PresetConfig (EL:DefaultConfig (EL:DrawingID)))))))
    (progn
      (setq pd (entget (car panel)))
      (EL:LogEvent "SIMPLE_PICKS" (list (EL:LogEntity (car panel))))
      (princ "\n正在识别所选配电箱连接的设备...")
      (setq snapshot (EL:LogCall "SIMPLE_COLLECT" (EL:Get 'wire-layers cfg) 'EL:SimpleCollect (list cfg))
            result (EL:LogCall "SIMPLE_NETWORK" (cdr (assoc 5 pd)) 'EL:SimpleNetwork (list snapshot cfg (cdr (assoc 5 pd)))))
      (EL:ClearPickHighlights)
      (EL:LogEvent "SIMPLE_RESULT" (list (cons 'device-count (length (EL:Get 'devices result)))
        (cons 'wire-count (length (EL:Get 'wire-ids result))) (cons 'gap-count (length (EL:Get 'gap-pairs result)))
        (cons 'gap-issues (EL:Get 'gap-issues result))))
      (if (EL:Get 'devices result)
        (progn (setq *EL:DeviceResult* result) (EL:SimpleEdit result))
        (princ "\n未找到与该配电箱连通的设备，请检查所选导线图层和箱口接线。"))))
  (EL:ClearPickHighlights) (EL:LogFinish (if *EL:DeviceResult* 'device-table 'no-devices)) (princ))
(princ)

;; Date: 2026-10-11. An isolated free end is not evidence of a broken connection.
(defun EL:SimpleBlockingGapIssues (issues)
  (vl-remove-if '(lambda (issue)
    (and (equal (EL:Get 'code issue) 'NO_CANDIDATE)
      (not (EL:Get 'candidates (EL:Get 'detail issue)))
      (not (EL:Get 'rejected (EL:Get 'detail issue))))) issues))
