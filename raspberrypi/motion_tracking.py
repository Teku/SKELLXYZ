"""Foreground motion detection and conservative target association."""
import math


def center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


class StableTarget:
    def __init__(self, hold_seconds=.8):
        self.hold_seconds = hold_seconds
        self.point = self.box = None
        self.seen = None
        self.candidate = None
        self.hits = 0
        self.candidate_time = 0
        self.state = "NO TARGET"

    def reset(self):
        self.__init__(self.hold_seconds)

    def update(self, boxes, now):
        if self.seen is not None and now - self.seen > self.hold_seconds:
            self.reset()
        chosen = None
        if self.box is not None:
            old = center(self.box)
            gate = max(40, min(100, self.box[2] * .8))
            matches = sorted((math.hypot(center(b)[0]-old[0], center(b)[1]-old[1]), b) for b in boxes)
            if matches and matches[0][0] < gate:
                if len(matches) == 1 or matches[1][0] - matches[0][0] > 15:
                    chosen = matches[0][1]
        elif len(boxes) == 1:
            box = boxes[0]
            if self.candidate is not None and now - self.candidate_time < 2.5 and math.hypot(center(box)[0]-center(self.candidate)[0], center(box)[1]-center(self.candidate)[1]) < 60:
                self.hits += 1
            else:
                self.hits = 1
            self.candidate, self.candidate_time = box, now
            if self.hits >= 3:
                chosen = box
        else:
            self.candidate, self.hits = None, 0
        if chosen is not None:
            point = center(chosen)
            alpha = 1 if self.seen is None else 1 - math.exp(-min(1, now-self.seen)/.3)
            self.point = point if self.point is None else tuple(a + alpha*(b-a) for a,b in zip(self.point, point))
            self.box, self.seen = chosen, now
            self.state = "TRACKING"
            return self.point
        if self.point is not None:
            self.state = "HOLDING"
            return self.point
        self.state = "CONFIRMING" if len(boxes) == 1 else "CROWD/NO LOCK" if boxes else "NO TARGET"
        return None


class MotionDetector:
    def __init__(self, cv2, settings):
        self.cv = cv2
        self.settings = settings
        self.model = cv2.createBackgroundSubtractorMOG2(history=150, varThreshold=25, detectShadows=True)
        self.started = None
        self.frames = 0
        self.state = "WARMING UP"
        self.region = None

    def detect(self, frame, now):
        cv, s = self.cv, self.settings
        h, w = frame.shape[:2]
        left, right = int(w*s["roi_left"]/100), int(w*s["roi_right"]/100)
        top, bottom = int(h*s["roi_top"]/100), int(h*s["roi_bottom"]/100)
        self.region = (left, top, right-left, bottom-top)
        crop = cv.GaussianBlur(frame[top:bottom, left:right], (5,5), 0)
        if self.started is None:
            self.started = now
        self.frames += 1
        warming = now-self.started < 3 or self.frames < 10
        mask = self.model.apply(crop, learningRate=.15 if warming else .005)
        # MOG2 marks shadows 127; retain only definite foreground (255).
        mask = cv.threshold(mask, 200, 255, cv.THRESH_BINARY)[1]
        if warming:
            self.state = "WARMING UP"
            return []
        if cv.countNonZero(mask) / mask.size > .45:
            self.state = "LIGHT/SCENE CHANGE"
            self.model.apply(crop, learningRate=.25)
            return []
        kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5,5))
        mask = cv.morphologyEx(mask, cv.MORPH_OPEN, kernel)
        mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=2)
        contours = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)[-2]
        boxes = []
        for contour in contours:
            area = cv.contourArea(contour)
            x,y,bw,bh = cv.boundingRect(contour)
            if mask.size*s["min_area"]/100 <= area <= mask.size*.4 and bw >= 8 and bh >= 12:
                boxes.append((x+left, y+top, bw, bh))
        self.state = "READY"
        return boxes
