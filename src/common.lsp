;; AutoCAD 2021+, LISPSYS=1/2. Pure functions shared by CAD and host checks.
(defun EL:Get (key data) (cdr (assoc key data)))
(defun EL:Put (key value data / old)
  (if (setq old (assoc key data))
    (subst (cons key value) old data)
    (append data (list (cons key value)))))
(defun EL:Unique (items / out item)
  (foreach item items (if (not (member item out)) (setq out (cons item out))))
  (reverse out))
(defun EL:Issue (code object detail)
  (list (cons 'code code) (cons 'object object) (cons 'detail detail)))
(defun EL:Number (x) (and (numberp x) (= x x) (< (abs x) 1.0e100)))
(defun EL:NonNegative (x) (and (EL:Number x) (>= x 0)))
(defun EL:Point (p)
  (and (listp p) (= (length p) 3)
       (EL:Number (car p)) (EL:Number (cadr p)) (EL:Number (caddr p))))
(defun EL:Point3 (p) (list (car p) (cadr p) (cond ((caddr p)) (T 0.0))))
(defun EL:V+ (a b) (mapcar '+ a b))
(defun EL:V- (a b) (mapcar '- a b))
(defun EL:V* (s a) (mapcar '(lambda (v) (* s v)) a))
(defun EL:Dot (a b) (apply '+ (mapcar '* a b)))
(defun EL:Cross (a b) (- (* (car a) (cadr b)) (* (cadr a) (car b))))
(defun EL:Norm (v) (sqrt (EL:Dot v v)))
(defun EL:Unit (v / n)
  (if (> (setq n (EL:Norm v)) 1.0e-9) (EL:V* (/ 1.0 n) v)))
(defun EL:Last (xs) (car (reverse xs)))
(defun EL:Strings (xs / ok x)
  (setq ok (listp xs))
  (foreach x xs (if (not (equal (type x) 'STR)) (setq ok nil))) ok)
(defun EL:ParamsValid (p / ok key)
  (setq ok T)
  (foreach key '(eps_touch eps_boundary eps_perp eps_z theta_max R0 Dmax)
    (if (not (EL:NonNegative (EL:Get key p))) (setq ok nil)))
  (and ok (< (EL:Get 'theta_max p) (/ pi 2.0))
       (> (EL:Get 'R0 p) 0) (<= (EL:Get 'R0 p) (EL:Get 'Dmax p))
       (> (EL:Get 'Dmax p) (EL:Get 'eps_touch p))))
(defun EL:LayerAllowed (a b config)
  (and (member a (EL:Get 'wire-layers config))
       (member b (EL:Get 'wire-layers config))
       (or (equal a b) (member (list a b) (EL:Get 'layer-pairs config))
           (member (list b a) (EL:Get 'layer-pairs config)))))
(defun EL:Hash (s / h n)
  (setq h 5381)
  (foreach n (vl-string->list s) (setq h (rem (+ (* h 33.0) n) 2147483629.0)))
  (rtos h 2 0))
(defun EL:StableData (data / tail items result item)
  ;; Date: 2026-10-09. Iterate list tails: stack depth follows nesting, not entity count.
  (cond ((equal (type data) 'ENAME) (list 'handle (cdr (assoc 5 (entget data)))))
        ((listp data)
          (setq tail data)
          (while (and tail (listp tail))
            (setq items (cons (EL:StableData (car tail)) items) tail (cdr tail)))
          (setq result (if tail (EL:StableData tail)))
          (foreach item items (setq result (cons item result))) result)
        (T data)))
(defun EL:Signature (data) (vl-prin1-to-string (EL:StableData data)))
(defun EL:RecognitionRules (cfg / rows key)
  (foreach key '(wire-styles auto-panel concentrated-trunk wire-layers panel-layers device-layers leader-layers panel-names device-names leader-names
      layer-pairs params calibrated gap-pairs leader-pairs roles exits)
    (setq rows (cons (cons key (EL:Get key cfg)) rows)))
  (cons '(box-policy . 20) (cons '(gap-policy . 10) (reverse rows))))
;; Date: 2026-10-11. Report which freshness condition failed.
(defun EL:SourceCurrent (result cfg fresh / drawing rules snapshot)
  (setq drawing (equal (EL:Get 'drawing result) (EL:Get 'drawing cfg))
    rules (equal (EL:Get 'rules result) (EL:RecognitionRules cfg))
    snapshot (equal (EL:Get 'signature fresh) (EL:Get 'signature (EL:Get 'snapshot result))))
  (if (not (and drawing rules snapshot))
    (EL:LogEvent "SOURCE_COMPARE_FAILED" (list (cons 'drawing-equal drawing)
      (cons 'rules-equal rules) (cons 'snapshot-equal snapshot))))
  (if (not snapshot) (EL:LogSnapshotDifference (EL:Get 'snapshot result) fresh))
  (and drawing rules snapshot))
(defun EL:OptionLabel (option)
  (cond ((equal option 'cap300) "0.3kW") ((equal option 'cap600) "0.6kW") ((equal option 'cap1000) "1kW")
        ((equal option 'normal) "普通") ((equal option 'ground) "地面") ((equal option 'reserve) "预留") (T "未选择")))
(defun EL:OnlyKeys (data keys / ok row seen)
  (setq ok (listp data))
  (foreach row data
    (if (or (not (listp row)) (not (member (car row) keys)) (member (car row) seen))
      (setq ok nil))
    (setq seen (cons (car row) seen))) ok)
(princ)

(defun EL:Tick (/ value)
  (setq value (vl-catch-all-apply 'getvar (list "MILLISECS")))
  (if (numberp value) value 0))
(defun EL:Elapsed (start) (max 0 (- (EL:Tick) start)))

;; Date: 2026-10-11. Command-scoped P0 counters, independent of business logs.
;; Inclusive stages overlap; user intervals are a union and are never summed twice.
(defun EL:PerfDelta (start stop)
  (if (< stop start) (+ (- stop start) 4294967296.0) (- stop start)))
(defun EL:PerfSet (key value)
  (if *EL:PerfActive* (setq *EL:PerfMetrics* (EL:Put key value *EL:PerfMetrics*))) nil)
(defun EL:PerfCount (key amount)
  (if *EL:PerfActive*
    (EL:PerfSet key (+ (cond ((EL:Get key *EL:PerfMetrics*)) (T 0)) amount))) nil)
(defun EL:PerfWaiting (/ elapsed)
  (setq elapsed *EL:PerfWaitMS*)
  (if (> *EL:PerfWaitDepth* 0)
    (setq elapsed (+ elapsed (EL:PerfDelta *EL:PerfWaitStart* (EL:Tick))))) elapsed)
(defun EL:PerfStart (commandname / stamp tick key)
  (if (not *EL:PerfActive*)
    (progn
      (setq tick (vl-catch-all-apply 'getvar (list "MILLISECS")))
      (setq *EL:PerfActive* T *EL:PerfCommand* commandname *EL:PerfStarted* (if (numberp tick) tick 0)
        *EL:PerfMetrics* nil *EL:PerfStages* nil *EL:PerfPending* nil *EL:PerfMarks* nil *EL:StoreReadCache* nil *EL:NetworkMemo* nil *EL:DLCache* nil *EL:DLSessionSnapshot* nil
        *EL:PerfWaitMS* 0 *EL:PerfWaitDepth* 0 *EL:PerfSerial* 0 *EL:PerfOutcome* nil
        *EL:StoreReadScope* (1+ (cond (*EL:StoreReadScope*) (T 0))))
      (setq stamp (vl-catch-all-apply 'getvar (list "CDATE")))
      (EL:PerfSet "date" (if (numberp stamp) stamp "unavailable"))
      (EL:PerfSet "clock-available" (if (numberp tick) T nil))
      (foreach key '("recognize-fixed-calls" "store-read-calls" "store-write-calls"
          "entity-write-attempts" "entity-write-returned" "master-write-attempts"
          "block-create-attempts" "text-create-attempts" "transaction-starts"
          "transaction-failures" "log-open-attempts" "log-write-attempts" "log-close-attempts" "panel-submits"
          "store-read-cache-hits" "store-read-cache-misses"
          "source-collect-calls" "source-selection-entities" "source-block-bounds-reads"
          "source-wire-record-reads" "device-contour-reads" "device-template-reuses"
          "network-build-calls" "network-verified-reuses" "network-geometry-checks"
          "number-scopes" "number-source-handles" "number-problems"
          "number-source-read-attempts" "number-source-read-failures" "number-freshness-checks"
          "device-library-loads" "device-library-writes" "device-library-matches" "device-library-unknown"
          "device-legend-loads" "device-legend-builds")
        (EL:PerfSet key 0)) T)))
(defun EL:PerfBegin (stage / token wait parent)
  (if *EL:PerfActive*
    (progn
      (setq wait (member stage '("USER_INPUT" "PLACEMENT_INPUT"))
        parent (if *EL:PerfPending* (EL:Get 'stage (car *EL:PerfPending*)))
        *EL:PerfSerial* (1+ *EL:PerfSerial*)
        token (list (cons 'id *EL:PerfSerial*) (cons 'stage stage) (cons 'start (EL:Tick))
          (cons 'wait-before (EL:PerfWaiting)) (cons 'interactive (if wait T nil)) (cons 'parent parent)))
      (if wait
        (progn
          (if (= *EL:PerfWaitDepth* 0) (setq *EL:PerfWaitStart* (EL:Get 'start token)))
          (setq *EL:PerfWaitDepth* (1+ *EL:PerfWaitDepth*))))
      (setq *EL:PerfPending* (cons token *EL:PerfPending*)) token)))
(defun EL:PerfEnd (token status / stage row elapsed waited key parents)
  (if (and *EL:PerfActive* token (member token *EL:PerfPending*))
    (progn
      (if (EL:Get 'interactive token)
        (progn
          (setq *EL:PerfWaitDepth* (1- *EL:PerfWaitDepth*))
          (if (= *EL:PerfWaitDepth* 0)
            (setq *EL:PerfWaitMS* (+ *EL:PerfWaitMS* (EL:PerfDelta *EL:PerfWaitStart* (EL:Tick)))))))
      (setq stage (EL:Get 'stage token) row (EL:Get stage *EL:PerfStages*)
        elapsed (EL:PerfDelta (EL:Get 'start token) (EL:Tick))
        waited (max 0 (- (EL:PerfWaiting) (EL:Get 'wait-before token))))
      (foreach key (list (cons 'calls 1) (cons 'inclusive-ms elapsed)
          (cons 'program-ms (max 0 (- elapsed waited))) (cons 'interrupted (if (equal status 'returned) 0 1)))
        (setq row (EL:Put (car key) (+ (cond ((EL:Get (car key) row)) (T 0)) (cdr key)) row)))
      (setq parents (EL:Get 'parents row))
      (if (and (EL:Get 'parent token) (not (member (EL:Get 'parent token) parents)))
        (setq row (EL:Put 'parents (cons (EL:Get 'parent token) parents) row)))
      (setq *EL:PerfStages* (EL:Put stage row *EL:PerfStages*)
        *EL:PerfPending* (vl-remove token *EL:PerfPending*)))) nil)
(defun EL:PerfUnwind (checkpoint)
  (while (and *EL:PerfPending* (not (equal checkpoint *EL:PerfPending*)))
    (EL:PerfEnd (car *EL:PerfPending*) 'interrupted)) nil)
(defun EL:FreshBoundary ()
  ;; Date: 2026-10-11. Input, native commands, writes and unknown callbacks
  ;; invalidate the current operation's sampled source; never cache a command.
  (setq *EL:FreshEpoch* (1+ (cond (*EL:FreshEpoch*) (T 0)))) nil)
(defun EL:PerfCall (stage function arguments / token result)
  (if (member stage '("USER_INPUT" "PLACEMENT_INPUT" "PANEL_DIALOG")) (EL:FreshBoundary))
  (if (and *EL:PerfActive* (or (member stage
      '("USER_INPUT" "PLACEMENT_INPUT" "PANEL_DIALOG" "RECOGNIZE_FIXED_RUN"
        "SIMPLE_COLLECT" "SIMPLE_NETWORK" "NETWORK_VERIFY_GEOMETRY" "NETWORK_BUILD" "SPLIT_NETWORK" "CIRCUIT_NUMBER_SCOPE"
        "COMPARE_SOURCE_NUMBER" "PRE_GENERATE_FRESH" "FRESH_SOURCE_SCAN"
        "CCKK2" "TX_WRITE" "STORE_READ" "STORE_DECODE" "STORE_CACHE_CHECK" "STORE_SERIALIZE"
        "STORE_PARSE" "STORE_READBACK" "STORE_CONTEXT_COMMIT" "STORE_CONTEXT_READ"
        "DIAGRAM_VIEW" "DIAGNOSTIC_EXPORT" "DEVICE_LIBRARY_LOAD" "DEVICE_LEGEND"))
      (and *EL:PerfDetail* (member stage
        '("STORE_SCHEMA" "STORE_REPLACE_PAYLOAD" "CCKK2_INSERT_BLOCK" "CCKK_POWER_TEXT"
          "TAG_ENTITY" "UNDO_BEGIN" "UNDO_END" "COMPARE_SOURCE" "SNAPSHOT_SIGNATURE" "CIRCUIT_TRACE")))))
    (setq token (EL:PerfBegin stage)))
  ;; Keep native return values and exceptions. Caught transactions unwind their frames.
  (setq result (apply function arguments))
  ;; A callback may sample the source and then change it during this input.
  ;; That sample cannot survive the return to the enclosing operation.
  (if (member stage '("USER_INPUT" "PLACEMENT_INPUT" "PANEL_DIALOG")) (EL:FreshBoundary))
  (EL:PerfEnd token 'returned)
  (if (and result (equal stage "PLACEMENT_INPUT")) (EL:PerfMark "placement-confirmed")) result)
(defun EL:PerfInput (function arguments)
  (EL:PerfCall "USER_INPUT" function arguments))
(defun EL:PerfWrite (function arguments / result)
  ;; Attempts count the actual interface invocation, including nil/error returns.
  (EL:FreshBoundary)
  (EL:PerfCount "entity-write-attempts" 1)
  (if *EL:PerfDetail* (EL:PerfCount (strcat "write/" (vl-symbol-name function)) 1))
  (setq result (apply function arguments))
  (EL:FreshBoundary)
  (EL:PerfCount "entity-write-returned" 1) result)
(defun EL:PerfMark (key)
  (if *EL:PerfActive*
    (setq *EL:PerfMarks* (EL:Put key (list (EL:Tick) (EL:PerfWaiting)) *EL:PerfMarks*))) nil)
(defun EL:PerfMarkDuration (key / mark elapsed)
  (if (setq mark (EL:Get key *EL:PerfMarks*))
    (progn (setq elapsed (EL:PerfDelta (car mark) (EL:Tick)))
      (list (cons 'inclusive-ms elapsed)
        (cons 'program-ms (max 0 (- elapsed (- (EL:PerfWaiting) (cadr mark)))))))))
(defun EL:PerfAppend (path line / file result closed)
  (if (setq file (open path "a" "utf8"))
    (progn
      (setq result (vl-catch-all-apply 'write-line (list line file))
        closed (vl-catch-all-apply 'close (list file)))
      (and (not (vl-catch-all-error-p result)) (not (vl-catch-all-error-p closed))))))
(defun EL:PerfReport (summary / path line written folder)
  (setq line (strcat "PERF | " (vl-prin1-to-string summary)))
  (if (and (equal (type *EL:Root*) 'STR) (/= *EL:Root* ""))
    (progn
      (vl-catch-all-apply 'vl-mkdir (list (strcat *EL:Root* "output")))
      (setq path (strcat *EL:Root* "output/ELPERF.log")
        written (vl-catch-all-apply 'EL:PerfAppend (list path line)))))
  (if (or (vl-catch-all-error-p written) (not written))
    (progn
      (setq folder (vl-catch-all-apply 'getvar (list "TEMPPREFIX")))
      (if (and (equal (type folder) 'STR) (/= folder ""))
        (setq path (strcat folder "ELPERF.log")
          written (vl-catch-all-apply 'EL:PerfAppend (list path line))))))
  (princ (strcat "\n性能汇总：总区间 " (itoa (fix (EL:Get 'total-ms summary)))
    " ms，交互区间 " (itoa (fix (EL:Get 'interaction-ms summary)))
    " ms，程序区间 " (itoa (fix (EL:Get 'program-ms summary))) " ms。"))
  (if (and (not (vl-catch-all-error-p written)) written)
    (princ (strcat "\n性能记录：" path))
    (princ "\n性能记录写入失败；汇总保留在 *EL:PerfLastSummary*。")) nil)
(defun EL:PerfFinish (status / elapsed waited summary)
  (if *EL:PerfActive*
    (progn
      (EL:PerfUnwind nil)
      (setq elapsed (EL:PerfDelta *EL:PerfStarted* (EL:Tick)) waited (EL:PerfWaiting)
        summary (list '(schema . 1) (cons 'command *EL:PerfCommand*) (cons 'status status)
          (cons 'last-outcome *EL:PerfOutcome*) (cons 'package *EL:PackageMarker*)
          (cons 'detail (if *EL:PerfDetail* T nil)) (cons 'business-logs (if *EL:PerfLogsOff* 'off 'on))
          (cons 'total-ms elapsed) (cons 'interaction-ms waited) (cons 'program-ms (max 0 (- elapsed waited)))
          (cons 'after-submit (EL:PerfMarkDuration "panel-submit"))
          (cons 'after-placement (EL:PerfMarkDuration "placement-confirmed"))
          (cons 'metrics *EL:PerfMetrics*) (cons 'stages *EL:PerfStages*)))
      ;; Snapshot before reporting: summary I/O is outside all business measurements.
      (setq *EL:PerfLastSummary* summary *EL:PerfActive* nil *EL:PerfPending* nil
        *EL:PerfMetrics* nil *EL:PerfStages* nil *EL:PerfMarks* nil *EL:PerfLogOwner* nil *EL:StoreReadCache* nil)
      (vl-catch-all-apply 'EL:PerfReport (list summary))))
  (setq *EL:StoreReadCache* nil *EL:NetworkMemo* nil *EL:DLCache* nil *EL:DLSessionSnapshot* nil) nil)
(defun c:ELPERF (/ option)
  (if *EL:PerfActive* (princ "\n请结束当前统计或生成后再调整性能采样。")
    (progn
      (princ (strcat "\n性能采样：" (if *EL:PerfDetail* "细分" "汇总")
        "；业务日志：" (if *EL:PerfLogsOff* "关闭（仅对照测量）" "开启")))
      (initget "LogsOn LogsOff Detail Summary")
      (setq option (getkword "\n[LogsOn开启日志/LogsOff关闭日志对照/Detail细分计量/Summary汇总计量] <保持>："))
      (cond ((equal option "LogsOn") (setq *EL:PerfLogsOff* nil))
        ((equal option "LogsOff") (setq *EL:PerfLogsOff* T))
        ((equal option "Detail") (setq *EL:PerfDetail* T))
        ((equal option "Summary") (setq *EL:PerfDetail* nil)))
      (princ "\n仅影响本次加载会话的测量；ELPERF.log 独立保留，日志对照结束后请恢复 LogsOn。"))) (princ))

;; Date: 2026-10-09. Diagnostics never change recognition or propagate I/O errors.
(defun EL:LogText (value / textdata)
  (setq textdata (vl-catch-all-apply 'vl-prin1-to-string (list value)))
  (if (vl-catch-all-error-p textdata) "<unprintable>"
    (if (> (strlen textdata) 16000) (strcat (substr textdata 1 16000) " <truncated>") textdata)))
(defun EL:LogAppend (line / logfile result closed started)
  (EL:PerfCount "log-open-attempts" 1)
  (if (and *EL:PerfActive* *EL:PerfDetail*) (setq started (EL:Tick)))
  (if (setq logfile (open *EL:LogPath* "a" "utf8"))
    (progn
      (EL:PerfCount "log-write-attempts" 1)
      (setq result (vl-catch-all-apply 'write-line (list line logfile)))
      (setq closed (vl-catch-all-apply 'close (list logfile)))
      (EL:PerfCount "log-close-attempts" 1)
      (if started (EL:PerfCount "log-io-ms" (EL:PerfDelta started (EL:Tick))))
      (and (not (vl-catch-all-error-p result)) (not (vl-catch-all-error-p closed))))))
;; Date: 2026-10-10. Retry in TEMP when the runtime output is unavailable.
(defun EL:LogFallback (line / folder previous result)
  (if (not *EL:LogFallbackUsed*)
    (progn
      (setq *EL:LogFallbackUsed* T previous *EL:LogPath*
        folder (vl-catch-all-apply 'getvar (list "TEMPPREFIX")))
      (if (and (equal (type folder) 'STR) (/= folder ""))
        (progn
          (setq *EL:LogPath* (strcat folder "ELTRACE-debug.log"))
          (setq result (vl-catch-all-apply 'EL:LogAppend
            (list (strcat "LOG_FALLBACK | original-path=" (EL:LogText previous)
              " | last-context=" (EL:LogText *EL:LogLast*) " | stack=" (EL:LogText *EL:LogStack*)))))
          (if (and (not (vl-catch-all-error-p result)) result)
            (setq result (vl-catch-all-apply 'EL:LogAppend (list line))))
          (and (not (vl-catch-all-error-p result)) result))))))
(defun EL:LogEvent (stage context / line result started)
  (if *EL:LogActive*
    (progn
      (setq *EL:LogSequence* (1+ *EL:LogSequence*)
            *EL:LogLast* (list stage context))
      ;; Keep current failure context in memory; avoid per-vertex file I/O by default.
      (if (and (not *EL:PerfLogsOff*) *EL:LogPath* (or *EL:LogVerbose* (not (member stage
          '("POLYLINE_DXF_ROW" "POLYLINE_SEGMENT" "POLYLINE_INPUT" "POLYLINE_DATA_RESULT"
            "ENTER POLYLINE_TRANS" "LEAVE POLYLINE_TRANS" "POLYLINE_TRANS_RESULT"
            "ENTER CURVE_TRANS" "LEAVE CURVE_TRANS" "CURVE_TRANS_RESULT"
            "ENTER INSERT_TRANS" "LEAVE INSERT_TRANS" "INSERT_TRANS_RESULT" "INSERT_MATRIX_INPUT"
            "ENTER SOLID_TRANS" "LEAVE SOLID_TRANS" "SOLID_TRANS_RESULT" "POLYLINE_NORMAL"
            "CONTOUR_ENTITY" "CONTOUR_FILTER_INPUT" "CONTOUR_NEXT"
            "ENTER CONTOUR_TRANSFORM" "LEAVE CONTOUR_TRANSFORM" "CONTOUR_TRANSFORM_RESULT")))))
        (progn
          (if (and *EL:PerfActive* *EL:PerfDetail*) (setq started (EL:Tick)))
          (setq line (strcat (itoa *EL:LogSequence*) " | " stage " | " (EL:LogText context)))
          (if started (EL:PerfCount "log-format-ms" (EL:PerfDelta started (EL:Tick))))
          (setq result (vl-catch-all-apply 'EL:LogAppend (list line)))
          (if (or (and (not (vl-catch-all-error-p result)) result) (EL:LogFallback line)) (setq *EL:LogWritten* T)
            (setq *EL:LogIOFailed* T *EL:LogPath* nil))))))
  nil)
(defun EL:LogStart (/ stamp)
  (setq *EL:PerfLogOwner* (EL:PerfStart "ELSTAT/ELTRACE/ELPOWER"))
  (setq *EL:LogActive* T *EL:LogPath* nil *EL:LogStack* nil *EL:LogLast* nil
        *EL:LogSequence* 0 *EL:LogWritten* nil *EL:LogIOFailed* nil *EL:LogFallbackUsed* nil)
  (EL:LogAttach)
  (setq stamp (vl-catch-all-apply 'getvar (list "CDATE")))
  (EL:LogEvent "BEGIN" (list (cons 'command "ELSTAT/ELTRACE/ELPOWER") (cons 'diagnostics "031") (cons 'verbose *EL:LogVerbose*)
    (cons 'date (if (numberp stamp) stamp "unavailable")))))
(defun EL:LogAttach (/ stamp)
  (if (and *EL:LogActive* (not *EL:LogPath*) (not *EL:LogIOFailed*)
           (equal (type *EL:Root*) 'STR) (/= *EL:Root* ""))
    (progn
      (vl-catch-all-apply 'vl-mkdir (list (strcat *EL:Root* "output")))
      (setq *EL:LogPath* (strcat *EL:Root* "output/ELTRACE-debug.log")
            stamp (vl-catch-all-apply 'getvar (list "CDATE")))
      (EL:LogEvent "ATTACH" (list (cons 'diagnostics "031")
        (cons 'date (if (numberp stamp) stamp "unavailable")))))))
(defun EL:LogCall (stage context function arguments / result started)
  ;; Leave the stack intact on an AutoLISP error; the command's *error* records it.
  (if *EL:LogActive*
    (progn (setq *EL:LogStack* (cons (list stage context) *EL:LogStack*))
      (EL:LogEvent (strcat "ENTER " stage) context)))
  (setq started (if *EL:LogActive* (EL:Tick)) result (EL:PerfCall stage function arguments))
  (if *EL:LogActive*
    (progn
      (EL:LogEvent (strcat "LEAVE " stage) (list (cons 'elapsed-ms (EL:Elapsed started)) (cons 'result-type (type result))))
      (setq *EL:LogStack* (cdr *EL:LogStack*))))
  result)
(defun EL:LogEntity (entity / data)
  (setq data (entget entity))
  (list (cons 'handle (cdr (assoc 5 data))) (cons 'type (cdr (assoc 0 data)))
    (cons 'layer (cdr (assoc 8 data))) (cons 'block (cdr (assoc 2 data)))
    (cons 'dxf (vl-remove-if-not '(lambda (pair) (member (car pair)
      '(0 2 5 8 10 11 38 40 41 42 43 50 51 60 70 90 210 410))) data))))
(defun EL:LogFinish (status)
  (if *EL:PerfActive* (setq *EL:PerfOutcome* status))
  (if *EL:LogActive*
    (progn
      (EL:LogEvent "END" status)
      (cond
        (*EL:PerfLogsOff* nil)
        (*EL:LogIOFailed* (princ "\n诊断日志写入失败；请保留命令行的失败阶段和上下文。"))
        (*EL:LogWritten* (princ (strcat "\n诊断日志：" *EL:LogPath*)))
        (T (princ "\n未建立日志文件；请保留命令行信息。")))))
  (setq *EL:LogActive* nil *EL:LogStack* nil)
  (if *EL:PerfLogOwner* (EL:PerfFinish status)))
(defun EL:LogFailure (message / laststate stack)
  (setq laststate *EL:LogLast* stack *EL:LogStack*)
  (EL:LogEvent "ERROR" (list (cons 'message message) (cons 'stack stack) (cons 'last-event laststate)))
  (princ (strcat "\n原始错误：" (EL:LogText message)
    "\n失败阶段：" (EL:LogText stack) "\n最后上下文：" (EL:LogText laststate)))
  (EL:LogFinish 'failed))

;; Date: 2026-10-09. Managed outputs never enter source recognition.
(defun EL:DiagramTag (entity / data)
  (if entity
    (progn (setq data (entget entity '("EL_FIXED_V1")))
      (cdr (assoc "EL_FIXED_V1" (cdr (assoc -3 data)))))))
(defun EL:ManagedEntity (entity) (if (EL:DiagramTag entity) T nil))

;; Date: 2026-10-11. Display numbers never replace persistent panel identity.
(defun EL:PanelNumber (data / value)
  (setq value (EL:Get 'panel-number data))
  (if (and (equal (type value) 'STR) (/= (vl-string-trim " \t\r\n" value) ""))
    value "暂无编号"))

;; Date: 2026-10-11. Bounded evidence for exact snapshot differences, without parsing long strings.
(defun EL:StringDifference (before after / index start)
  (if (and (equal (type before) 'STR) (equal (type after) 'STR))
    (progn
      (setq index (cond ((vl-string-mismatch before after)) (T 0)) start (max 1 (- (1+ index) 100)))
      (list (cons 'offset index) (cons 'before-length (strlen before)) (cons 'after-length (strlen after))
        (cons 'before (substr before start 240)) (cons 'after (substr after start 240))))
    (list (cons 'before-type (type before)) (cons 'after-type (type after)))))
(defun EL:LogSnapshotDifference (before after / key a b keys typed)
  (setq typed (or
    (and (listp (EL:Get 'signature before)) (equal (car (EL:Get 'signature before)) 'EL_FIXED_SOURCE_V1))
    (and (listp (EL:Get 'signature after)) (equal (car (EL:Get 'signature after)) 'EL_FIXED_SOURCE_V1))))
  (setq keys (EL:Unique (append (mapcar 'car before) (mapcar 'car after))))
  (foreach key keys
    (setq a (EL:Get key before) b (EL:Get key after))
    (if (not (equal a b))
      (EL:LogEvent "SOURCE_FIELD_DIFFERENCE" (list (cons 'field key)
        (cons 'difference
          (if typed
            ;; Reuse bounded typed readback diagnostics; never reprint the failing snapshot.
            (EL:StoreDifference a b (list key))
            (EL:StringDifference
              (if (equal (type a) 'STR) a (EL:Signature a))
              (if (equal (type b) 'STR) b (EL:Signature b))))))))))
