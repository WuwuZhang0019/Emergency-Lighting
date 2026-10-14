;; Date: 2026-10-15. Frozen 138 implementation (520e46b); test oracle only.
(defun oracle:SpatialTree (items axis / keyed item invalid)
  ;; Date: 2026-10-13. Compute stable tie-break keys once per item, not once
  ;; per sort comparison at every tree level (planar drawings share Z=0).
  (if *EL:LogActive*
    (progn
      (setq invalid (vl-remove-if '(lambda (row) (EL:Point (EL:Get 'point row))) items))
      (if invalid (EL:LogEvent "INDEX_INVALID_POINTS" (list axis invalid)))))
  (foreach item items
    (setq keyed (cons (cons (EL:Signature (EL:Get 'key item)) item) keyed)))
  (oracle:SpatialTreeBuild (reverse keyed) axis))

(defun oracle:SpatialTreeBuild (items axis / sorted mid i item pivot left right lo hi bounds)
  ;; Preserve the existing axis order, tie-break order and public tree layout.
  (if items
    (progn
      (setq sorted (vl-sort items '(lambda (a b)
        (if (= (nth axis (EL:Get 'point (cdr a))) (nth axis (EL:Get 'point (cdr b))))
          (< (car a) (car b))
          (< (nth axis (EL:Get 'point (cdr a))) (nth axis (EL:Get 'point (cdr b)))))))
            mid (/ (length sorted) 2) i 0)
      (foreach item sorted
        (cond ((< i mid) (setq left (cons item left)))
              ((= i mid) (setq pivot (cdr item))) (T (setq right (cons item right))))
        (setq i (1+ i)))
      (setq left (oracle:SpatialTreeBuild left (fix (rem (1+ axis) 3)))
            right (oracle:SpatialTreeBuild right (fix (rem (1+ axis) 3)))
            bounds (EL:Get 'bounds pivot)
            lo (if bounds (car bounds) (EL:Get 'point pivot))
            hi (if bounds (cadr bounds) lo))
      (foreach item (list left right)
        (if item (setq lo (mapcar 'min lo (nth 3 item)) hi (mapcar 'max hi (nth 4 item)))))
      (list pivot left right lo hi))))

(defun oracle:NumberPathSlice (wire start finish / low high cursor segment length a b part segments)
  (setq low (min start finish) high (max start finish) cursor 0.0)
  (foreach segment (EL:Get 'segments wire)
    (setq length (EL:Norm (EL:V- (cadr segment) (car segment)))
      a (max low cursor) b (min high (+ cursor length)))
    (if (and (> length 1.0e-12) (> b a))
      (progn
        (setq part (list
          (EL:V+ (car segment) (EL:V* (/ (- a cursor) length) (EL:V- (cadr segment) (car segment))))
          (EL:V+ (car segment) (EL:V* (/ (- b cursor) length) (EL:V- (cadr segment) (car segment))))))
        (setq segments (cons part segments))))
    (setq cursor (+ cursor length)))
  (setq segments (reverse segments))
  (if (> start finish) (setq segments (mapcar '(lambda (s) (reverse s)) (reverse segments))))
  (EL:Put 'contact-strips (EL:WireContactStrips segments (EL:Get 'width-profiles wire))
    (EL:Put 'segments segments wire)))

(defun oracle:NumberShapeHit (wire shape cfg)
  (or (EL:ContourPathHit wire shape (EL:StrictDeviceConfig cfg))
    (EL:WideDevicePathHit wire shape (EL:StrictDeviceConfig cfg))))

(defun oracle:NumberFirstDevice (wire entry target devices cfg / block shape candidate low high middle distance best)
  (if (> (abs (- target entry)) 1.0e-12)
    (foreach block devices
      (setq shape (EL:DeviceContactShape block))
      (if (oracle:NumberShapeHit (oracle:NumberPathSlice wire entry target) shape cfg)
        (progn
          ;; A growing prefix has monotone contact even with holes and multiple regions.
          (setq low 0.0 high 1.0)
          (repeat 32
            (setq middle (/ (+ low high) 2.0))
            (if (oracle:NumberShapeHit (oracle:NumberPathSlice wire entry (+ entry (* middle (- target entry)))) shape cfg)
              (setq high middle) (setq low middle)))
          (setq distance (+ entry (* high (- target entry))))
          (if (or (not best) (< (abs (- distance entry)) (abs (- (car best) entry))))
            (setq best (list distance (EL:Get 'id block)))))))) best)
