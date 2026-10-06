"""
MÊ CUNG BÓNG ĐÊM (góc nhìn thứ nhất) - Python + tkinter, 1 file, không cần cài thêm gì

Cách chơi:
  - WASD / Mũi tên : Di chuyển (Tiến, Lùi, Sang trái, Sang phải)
  - Chuột : Xoay góc nhìn (trái, phải)
  - Bạn chỉ soi sáng được quanh mình ~1 ô (như vùng 3x3), xa hơn là bóng tối
  - Đầu mỗi màn hiện TOÀN BỘ bản đồ 5 giây (có vị trí quái vật) để ghi nhớ đường
  - Bấm M để mở lại bản đồ, nhưng chỉ có số lần giới hạn mỗi màn (game tạm dừng lúc xem map)
  - Tìm cổng xanh lá (LỐI RA) để qua màn. Quái vật đánh 3 lần là chết -> chơi lại từ đầu
  - R: chơi lại | Enter / Space: đóng bản đồ, qua màn, chơi lại | Esc: thoát
"""

import math
import random
import time
import tkinter as tk
from collections import deque

# ===================== CẤU HÌNH (có thể chỉnh) =====================
VIEW_W, VIEW_H = 720, 480   # kích thước khung nhìn thứ nhất (pixel)
COL_W = 4                   # độ rộng 1 cột tia quét (nhỏ = đẹp hơn nhưng nặng hơn)
N_COLS = VIEW_W // COL_W
PLANE = 0.70                # độ rộng góc nhìn (FOV) ~ 70 độ
VISION = 7                # tầm soi sáng (đơn vị: ô). ~1.8 = thấy 1 ô xung quanh
FRAME_MS = 33               # ~30 khung hình / giây
MAX_STEPS = 6               # số ô tối đa mỗi tia quét đi qua

START_CELLS = 10            # màn 1: mê cung 20x20 "phòng" (~61x61 ô)
CELLS_PER_LEVEL = 3         # mỗi màn to thêm bao nhiêu
MAX_CELLS = 45
MAX_HP = 3                  # bị đánh 3 phát là chết
MONSTER_MS = 450            # quái vật hành động mỗi 450ms
MOVE_COOLDOWN = 0.17        # giây giữa 2 bước đi
CHASE_RANGE = 6             # quái vật bắt đầu đuổi khi bạn trong phạm vi này (số bước đi)
PREVIEW_SECONDS = 500         # đầu mỗi màn hiện toàn bộ bản đồ bao nhiêu giây
MAP_USES = 300                # số lần được bấm M để mở bản đồ trong mỗi màn
MAP_VIEW_SECONDS = 500        # mỗi lần mở bản đồ (phím M) xem được bao nhiêu giây

CAM_SPEED = 9.0             # tốc độ camera trượt tới ô mới (ô / giây)
TURN_SPEED = 9.0            # tốc độ camera xoay (rad / giây)
MON_SPEED = 4.5             # tốc độ quái vật trượt giữa 2 ô (ô / giây)

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
FACE = [(1, 0), (0, 1), (-1, 0), (0, -1)]   # 0=Đông 1=Nam 2=Tây 3=Bắc
FACE_NAMES = ["Đông", "Nam", "Tây", "Bắc"]

# Màu sắc
C_DARK = "#07070b"
WALL_RGB = (122, 132, 155)
FLOOR_RGB = (78, 66, 56)
CEIL_RGB = (44, 48, 66)
MON_RGB = (210, 40, 40)
EXIT_FRAME = (35, 150, 90)
EXIT_GLOW = (130, 255, 180)
# màu cho bản đồ nhìn từ trên xuống
C_WALL = "#6b7385"
C_FLOOR = "#2a3040"
C_EXIT = "#3ddc84"
C_PLAYER = "#4fc3f7"
C_MONSTER = "#e53935"


def rgb(c, b):
    return "#%02x%02x%02x" % (min(255, int(c[0] * b)), min(255, int(c[1] * b)),
                              min(255, int(c[2] * b)))


def light(d):
    """Độ sáng theo khoảng cách tới người chơi: gần = sáng, tới VISION = tối đen."""
    r = d / VISION
    return max(0.0, 1.0 - r * r)    # giảm dần êm: gần sáng rõ, sát mép tầm nhìn mới tối hẳn


def gen_maze(cells):
    """Sinh mê cung ngẫu nhiên (DFS backtracker). 1 = tường, 0 = đường đi.
    Mỗi "phòng" rộng 2x2 ô, tường dày 1 ô -> hành lang rộng 2 ô để lách qua quái vật."""
    n = 3 * cells + 1
    g = [[1] * n for _ in range(n)]

    def carve_room(cx, cy):
        for yy in (3 * cy + 1, 3 * cy + 2):
            for xx in (3 * cx + 1, 3 * cx + 2):
                g[yy][xx] = 0

    def open_wall(cx, cy, dx, dy):
        # đục bức tường giữa phòng (cx,cy) và phòng kề (cx+dx, cy+dy), rộng 2 ô
        if dx:
            wx = 3 * cx + 3 if dx > 0 else 3 * cx
            g[3 * cy + 1][wx] = 0
            g[3 * cy + 2][wx] = 0
        else:
            wy = 3 * cy + 3 if dy > 0 else 3 * cy
            g[wy][3 * cx + 1] = 0
            g[wy][3 * cx + 2] = 0

    visited = [[False] * cells for _ in range(cells)]
    visited[0][0] = True
    carve_room(0, 0)
    stack = [(0, 0)]
    while stack:
        x, y = stack[-1]
        nb = [(x + dx, y + dy, dx, dy) for dx, dy in DIRS
              if 0 <= x + dx < cells and 0 <= y + dy < cells
              and not visited[y + dy][x + dx]]
        if nb:
            nx, ny, dx, dy = random.choice(nb)
            open_wall(x, y, dx, dy)
            carve_room(nx, ny)
            visited[ny][nx] = True
            stack.append((nx, ny))
        else:
            stack.pop()

    # Đục thêm vài đường tắt để có vòng lặp (đỡ bị quái vật dồn vào ngõ cụt)
    for _ in range(cells * cells // 10):
        x = random.randrange(cells)
        y = random.randrange(cells)
        dx, dy = random.choice(DIRS)
        if 0 <= x + dx < cells and 0 <= y + dy < cells:
            open_wall(x, y, dx, dy)
    return g


class Game:
    def __init__(self, root):
        self.root = root
        root.title("Mê Cung Bóng Đêm")
        root.configure(bg="#12141c")
        root.resizable(False, False)

        self.hud = tk.Label(root, font=("Arial", 13, "bold"), bg="#12141c",
                            fg="white", pady=6, height=2)
        self.hud.pack(fill="x")
        self.hud_text = ""

        self.canvas = tk.Canvas(root, width=VIEW_W, height=VIEW_H, bg=C_DARK,
                                highlightthickness=0)
        self.canvas.pack()

        tk.Label(root,
                 text="WASD / Mũi tên: di chuyển  |  Chuột: xoay  |  "
                      "M: bản đồ  |  R: chơi lại  |  Esc: thoát",
                 font=("Arial", 10), bg="#12141c", fg="#9aa3b5", pady=4).pack(fill="x")

        root.bind("<Key>", self.on_key)
        root.bind("<Motion>", self.on_mouse)

        self.level = 1
        self.state = "playing"      # preview | playing | dead | won
        self.last_move = 0.0
        self.flash_until = 0.0
        self.preview_end = 0.0
        self.preview_last = -1
        self.preview_title = ""
        self.no_map_until = 0.0
        self.map_uses = MAP_USES
        self.view_built = False
        self.col_items = []
        self.col_cache = []
        self.last_frame = time.time()

        self.new_level()
        self.monster_tick()
        self.frame()

    # ---------------------- Khởi tạo màn chơi ----------------------
    def new_level(self):
        cells = min(START_CELLS + (self.level - 1) * CELLS_PER_LEVEL, MAX_CELLS)
        self.grid = gen_maze(cells)
        self.n = len(self.grid)
        self.exit = (self.n - 2, self.n - 2)
        self.reset()

    def reset(self):
        """Đặt lại nhân vật + quái vật (giữ nguyên mê cung hiện tại)."""
        self.px, self.py = 1, 1
        self.facing = 0
        self.cam_x, self.cam_y = 1.5, 1.5
        self.cam_a = 0.0
        self.target_a = 0.0
        self.hp = MAX_HP
        self.steps = 0
        self.state = "preview"      # hiện toàn bộ bản đồ trước, rồi mới vào chơi
        self.preview_end = time.time() + PREVIEW_SECONDS
        self.preview_last = -1
        self.preview_title = "GHI NHỚ ĐƯỜNG ĐI!"
        self.map_uses = MAP_USES
        self.flash_until = 0.0

        floors = [(x, y) for y in range(1, self.n - 1) for x in range(1, self.n - 1)
                  if self.grid[y][x] == 0]
        random.shuffle(floors)
        count = 5 + self.level * 2
        self.monsters = []
        for (x, y) in floors:
            if len(self.monsters) >= count:
                break
            # không đặt quái quá gần điểm xuất phát hoặc lối ra
            if abs(x - 1) + abs(y - 1) < 10 or (x, y) == self.exit:
                continue
            self.monsters.append({"x": x, "y": y, "cd": 1,
                                  "fx": x + 0.5, "fy": y + 0.5})
        self.draw_preview()

    # ---------------------- Tiện ích ----------------------
    def free(self, x, y):
        return 0 <= x < self.n and 0 <= y < self.n and self.grid[y][x] == 0

    def monster_at(self, x, y):
        return any(m["x"] == x and m["y"] == y for m in self.monsters)

    def dist_map(self, limit):
        """BFS từ người chơi, trả về khoảng cách (số bước) tới các ô trong phạm vi."""
        d = {(self.px, self.py): 0}
        q = deque([(self.px, self.py)])
        while q:
            x, y = q.popleft()
            if d[(x, y)] >= limit:
                continue
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if self.free(nx, ny) and (nx, ny) not in d:
                    d[(nx, ny)] = d[(x, y)] + 1
                    q.append((nx, ny))
        return d

    def set_hud(self, text):
        if text != self.hud_text:
            self.hud_text = text
            self.hud.config(text=text)

    # ---------------------- Điều khiển ----------------------
    def try_move(self, direction):
        now = time.time()
        if now - self.last_move < MOVE_COOLDOWN:
            return
        dx, dy = FACE[direction]
        nx, ny = self.px + dx, self.py + dy
        if self.free(nx, ny) and not self.monster_at(nx, ny):
            self.last_move = now
            self.px, self.py = nx, ny
            self.steps += 1
            if (nx, ny) == self.exit:
                self.state = "won"

    def open_map(self, seconds):
        """Mở bản đồ toàn cảnh (game tạm dừng trong lúc xem)."""
        self.state = "preview"
        self.preview_end = time.time() + seconds
        self.preview_last = -1
        self.preview_title = "BẢN ĐỒ"
        self.draw_preview()

    def on_mouse(self, e):
        # Không xử lý chuột nếu đang xem bản đồ hoặc đã chết
        if self.state != "playing":
            return

        cx, cy = VIEW_W // 2, VIEW_H // 2
        
        # Bỏ qua sự kiện nếu chuột vừa được hệ thống warp về giữa
        if e.x == cx and e.y == cy:
            return

        dx = e.x - cx
        if dx != 0:
            # Điều chỉnh độ nhạy chuột
            self.target_a += dx * 0.003
            self.cam_a = self.target_a
            
            # Đồng bộ hướng camera với 4 hướng di chuyển
            normalized_a = self.target_a % (2 * math.pi)
            self.facing = int(round(normalized_a / (math.pi / 2))) % 4

        # Kéo chuột ngược về giữa khung hình
        self.root.event_generate('<Motion>', warp=True, x=cx, y=cy)

    def on_key(self, e):
        k = e.keysym.lower()
        if k == "escape":
            self.root.destroy()
            return
        if k == "r":
            self.reset()
            return
        if self.state == "preview":
            if k in ("return", "kp_enter", "space", "m"):
                self.state = "playing"   # đóng bản đồ sớm
            return
        if k in ("return", "kp_enter"):
            if self.state == "won":
                self.level += 1
                self.new_level()
            elif self.state == "dead":
                self.reset()
            return
        if self.state != "playing":
            return
        if k == "m":
            if self.map_uses > 0:
                self.map_uses -= 1
                self.open_map(MAP_VIEW_SECONDS)
            else:
                self.no_map_until = time.time() + 1.5
            return

        if k in ("up", "w"):
            self.try_move(self.facing)
        elif k in ("down", "s"):
            self.try_move((self.facing + 2) % 4)
        elif k in ("left", "a", "q"):
            self.try_move((self.facing + 3) % 4)
        elif k in ("right", "d", "e"):
            self.try_move((self.facing + 1) % 4)

    # ---------------------- Quái vật ----------------------
    def monster_tick(self):
        if self.state == "playing":
            d = self.dist_map(CHASE_RANGE)
            occupied = {(m["x"], m["y"]) for m in self.monsters}
            occupied.add((self.px, self.py))
            hit = False

            for m in self.monsters:
                pos = (m["x"], m["y"])
                dist = d.get(pos)

                if dist == 1:
                    # đứng cạnh người chơi -> tấn công (có thời gian chờ)
                    if m["cd"] > 0:
                        m["cd"] -= 1
                    else:
                        self.hp -= 1
                        hit = True
                        m["cd"] = 1
                    continue

                m["cd"] = 1  # vừa tới gần thì chưa đánh ngay
                target = None
                if dist is not None:
                    # đuổi theo: đi tới ô láng giềng gần người chơi hơn
                    best = dist
                    for dx, dy in DIRS:
                        np_ = (m["x"] + dx, m["y"] + dy)
                        if np_ in d and d[np_] < best and np_ not in occupied:
                            best = d[np_]
                            target = np_
                elif random.random() < 0.5:
                    # lang thang ngẫu nhiên
                    opts = [(m["x"] + dx, m["y"] + dy) for dx, dy in DIRS
                            if self.free(m["x"] + dx, m["y"] + dy)
                            and (m["x"] + dx, m["y"] + dy) not in occupied]
                    if opts:
                        target = random.choice(opts)

                if target:
                    occupied.discard(pos)
                    m["x"], m["y"] = target
                    occupied.add(target)

            if hit:
                self.flash_until = time.time() + 0.25
                if self.hp <= 0:
                    self.hp = 0
                    self.state = "dead"

        self.root.after(MONSTER_MS, self.monster_tick)

    # ---------------------- Vòng lặp hiển thị ----------------------
    def frame(self):
        now = time.time()
        dt = min(now - self.last_frame, 0.1)
        self.last_frame = now

        if self.state == "preview":
            left = self.preview_end - now
            if left <= 0:
                self.state = "playing"
            elif int(left) + 1 != self.preview_last:
                self.draw_preview()   # cập nhật đếm ngược

        if self.state != "preview":
            if not self.view_built:
                self.build_view()
            self.animate(dt)
            self.render()
            self.update_hud()

        # Ẩn chuột khi đang chơi
        if self.state == "playing":
            self.root.config(cursor="none")
        else:
            self.root.config(cursor="")

        self.root.after(FRAME_MS, self.frame)

    def animate(self, dt):
        """Camera và quái vật trượt mượt tới vị trí/hướng mới."""
        tx, ty = self.px + 0.5, self.py + 0.5
        dx, dy = tx - self.cam_x, ty - self.cam_y
        dist = math.hypot(dx, dy)
        step = CAM_SPEED * dt
        if dist <= step:
            self.cam_x, self.cam_y = tx, ty
        else:
            self.cam_x += dx / dist * step
            self.cam_y += dy / dist * step

        da = self.target_a - self.cam_a
        sa = TURN_SPEED * dt
        if abs(da) <= sa:
            self.cam_a = self.target_a
        else:
            self.cam_a += sa if da > 0 else -sa

        ms = MON_SPEED * dt
        for m in self.monsters:
            mx, my = m["x"] + 0.5 - m["fx"], m["y"] + 0.5 - m["fy"]
            md = math.hypot(mx, my)
            if md <= ms:
                m["fx"], m["fy"] = m["x"] + 0.5, m["y"] + 0.5
            else:
                m["fx"] += mx / md * ms
                m["fy"] += my / md * ms

    def update_hud(self):
        hearts = "♥" * self.hp + "♡" * (MAX_HP - self.hp)
        if time.time() < self.no_map_until:
            line2 = "HẾT LƯỢT MỞ BẢN ĐỒ!"
        else:
            line2 = f"Bản đồ {self.n}x{self.n}   |   Mở map (M): còn {self.map_uses} lần"
        self.set_hud(f"Màn {self.level}   |   Máu: {hearts}   |   Bước: {self.steps}\n{line2}")

    # ---------------------- Vẽ góc nhìn thứ nhất ----------------------
    def build_view(self):
        """Tạo sẵn nền (trần + sàn) và các cột tường; mỗi khung hình chỉ cập nhật lại."""
        c = self.canvas
        c.delete("all")
        half = VIEW_H // 2
        c.create_rectangle(0, 0, VIEW_W, VIEW_H, fill=C_DARK, outline="")
        step = 4
        for y in range(half, VIEW_H, step):
            ym = y + step / 2
            d = half / (ym - half)          # khoảng cách tới điểm sàn ở hàng này
            b = light(d)
            if b <= 0:
                continue
            c.create_rectangle(0, y, VIEW_W, y + step, fill=rgb(FLOOR_RGB, b), outline="")
            yc = VIEW_H - y - step
            c.create_rectangle(0, yc, VIEW_W, yc + step, fill=rgb(CEIL_RGB, b), outline="")
        self.col_items = []
        for i in range(N_COLS):
            it = c.create_rectangle(i * COL_W, half, (i + 1) * COL_W, half,
                                    fill=C_DARK, outline="")
            self.col_items.append(it)
        self.col_cache = [None] * N_COLS
        self.view_built = True

    def cast(self, rdx, rdy):
        """Bắn 1 tia (thuật toán DDA). Trả về (khoảng cách vuông góc, mặt tường, vị trí trên tường)."""
        cx, cy = self.cam_x, self.cam_y
        mx, my = int(cx), int(cy)
        ddx = abs(1.0 / rdx) if rdx != 0 else 1e30
        ddy = abs(1.0 / rdy) if rdy != 0 else 1e30
        if rdx < 0:
            sx, sdx = -1, (cx - mx) * ddx
        else:
            sx, sdx = 1, (mx + 1.0 - cx) * ddx
        if rdy < 0:
            sy, sdy = -1, (cy - my) * ddy
        else:
            sy, sdy = 1, (my + 1.0 - cy) * ddy
        grid, n = self.grid, self.n
        side = 0
        for _ in range(MAX_STEPS):
            if sdx < sdy:
                sdx += ddx
                mx += sx
                side = 0
            else:
                sdy += ddy
                my += sy
                side = 1
            if mx < 0 or my < 0 or mx >= n or my >= n or grid[my][mx] == 1:
                t = sdx - ddx if side == 0 else sdy - ddy
                wx = (cy + t * rdy) if side == 0 else (cx + t * rdx)
                return t, side, wx - math.floor(wx)
        return None

    def render(self):
        c = self.canvas
        half = VIEW_H // 2
        a = self.cam_a
        dx, dy = math.cos(a), math.sin(a)
        plx, ply = -dy * PLANE, dx * PLANE
        zbuf = [1e9] * N_COLS
        cache = self.col_cache

        for i in range(N_COLS):
            cam = 2.0 * (i + 0.5) / N_COLS - 1.0
            rdx, rdy = dx + plx * cam, dy + ply * cam
            res = self.cast(rdx, rdy)
            key = None
            if res is not None:
                t, side, wx = res
                t = max(t, 0.05)
                zbuf[i] = t
                b = light(t * math.hypot(rdx, rdy))
                if b > 0:
                    if side:
                        b *= 0.78
                    if (wx * 3) % 1 < 0.05:      # vạch gạch dọc cho có chất liệu
                        b *= 0.7
                    h = VIEW_H / t
                    key = (int(half - h / 2), int(half + h / 2), rgb(WALL_RGB, b))
            if key != cache[i]:
                cache[i] = key
                x0 = i * COL_W
                it = self.col_items[i]
                if key is None:
                    c.coords(it, x0, half, x0 + COL_W, half)
                else:
                    c.coords(it, x0, key[0], x0 + COL_W, key[1])
                    c.itemconfigure(it, fill=key[2])

        self.draw_sprites(zbuf, dx, dy, plx, ply)
        self.draw_overlay()

    def draw_sprites(self, zbuf, dx, dy, plx, ply):
        """Vẽ cổng lối ra và quái vật (billboard), có che khuất bởi tường."""
        c = self.canvas
        c.delete("sprite")
        det = plx * dy - dx * ply
        if abs(det) < 1e-9:
            return
        inv = 1.0 / det
        half = VIEW_H // 2

        targets = [(self.exit[0] + 0.5, self.exit[1] + 0.5, "exit")]
        for m in self.monsters:
            targets.append((m["fx"], m["fy"], "mon"))

        vis = []
        for sx, sy, kind in targets:
            rx, ry = sx - self.cam_x, sy - self.cam_y
            dist = math.hypot(rx, ry)
            if dist > VISION:
                continue
            tx = inv * (dy * rx - dx * ry)
            ty = inv * (-ply * rx + plx * ry)
            if ty < 0.15:
                continue
            vis.append((ty, tx, dist, kind))
        vis.sort(key=lambda v: -v[0])   # vẽ từ xa tới gần

        now = time.time()
        for ty, tx, dist, kind in vis:
            scr_x = VIEW_W / 2 * (1 + tx / ty)
            u = VIEW_H / ty                 # chiều cao 1 bức tường ở khoảng cách này
            bottom = half + u / 2           # chân đứng trên sàn
            b = 0.35 + 0.65 * light(dist)
            if kind == "mon":
                sw, sh = u * 0.62, u * 0.78
            else:
                sw, sh = u * 0.70, u * 0.95
            c0 = max(0, int((scr_x - sw / 2) // COL_W))
            c1 = min(N_COLS - 1, int((scr_x + sw / 2) // COL_W))
            pulse = 0.85 + 0.15 * math.sin(now * 4)

            for col in range(c0, c1 + 1):
                if ty >= zbuf[col]:
                    continue                # bị tường che
                xl = col * COL_W
                uu = (xl + COL_W / 2 - scr_x) / (sw / 2)
                if uu * uu >= 1:
                    continue
                hh = math.sqrt(1 - uu * uu)
                if kind == "mon":
                    top = bottom - sh * (0.15 + 0.85 * hh)
                    c.create_rectangle(xl, top, xl + COL_W, bottom,
                                       fill=rgb(MON_RGB, b * (0.7 + 0.3 * hh)),
                                       outline="", tags="sprite")
                else:
                    bb = max(b, 0.7) * pulse
                    top = bottom - sh * (0.8 + 0.2 * hh)
                    c.create_rectangle(xl, top, xl + COL_W, bottom,
                                       fill=rgb(EXIT_FRAME, bb), outline="", tags="sprite")
                    if abs(uu) < 0.7:
                        c.create_rectangle(xl, top + sh * 0.1, xl + COL_W, bottom,
                                           fill=rgb(EXIT_GLOW, bb), outline="", tags="sprite")

            # mắt + miệng quái vật
            ccol = int(scr_x // COL_W)
            if kind == "mon" and 0 <= ccol < N_COLS and ty < zbuf[ccol]:
                ey = bottom - sh * 0.62
                r = max(2.0, sw * 0.08)
                for ex in (scr_x - sw * 0.2, scr_x + sw * 0.2):
                    c.create_oval(ex - r, ey - r, ex + r, ey + r, fill="#ffe14d",
                                  outline="", tags="sprite")
                    c.create_oval(ex - r * 0.4, ey - r * 0.4, ex + r * 0.4, ey + r * 0.4,
                                  fill="#201000", outline="", tags="sprite")
                my_ = bottom - sh * 0.35
                c.create_rectangle(scr_x - sw * 0.22, my_, scr_x + sw * 0.22,
                                   my_ + max(3.0, sh * 0.06), fill="#1a0505",
                                   outline="", tags="sprite")

    def draw_overlay(self):
        c = self.canvas
        c.delete("overlay")
        c.create_text(VIEW_W - 14, 10, text=f"Hướng: {FACE_NAMES[self.facing]}", anchor="ne",
                      fill="#9aa3b5", font=("Arial", 12, "bold"), tags="overlay")
        if time.time() < self.flash_until:   # viền đỏ khi bị đánh
            w = 16
            for x0, y0, x1, y1 in ((0, 0, VIEW_W, w), (0, VIEW_H - w, VIEW_W, VIEW_H),
                                   (0, 0, w, VIEW_H), (VIEW_W - w, 0, VIEW_W, VIEW_H)):
                c.create_rectangle(x0, y0, x1, y1, fill="#ff1744", outline="", tags="overlay")
        if self.state == "won":
            self.overlay("QUA MÀN!", f"Bạn thoát ra sau {self.steps} bước\n"
                                     "Nhấn Enter để sang màn tiếp theo", "#3ddc84")
        elif self.state == "dead":
            self.overlay("BẠN ĐÃ CHẾT!", "Quái vật đã hạ gục bạn\n"
                                         "Nhấn Enter hoặc R để chơi lại từ đầu", "#ff5252")

    def overlay(self, title, sub, color):
        c = self.canvas
        cx, cy = VIEW_W // 2, VIEW_H // 2
        c.create_rectangle(cx - 250, cy - 90, cx + 250, cy + 90, fill="#0d0f16",
                           outline=color, width=4, tags="overlay")
        c.create_text(cx, cy - 35, text=title, fill=color, font=("Arial", 28, "bold"),
                      tags="overlay")
        c.create_text(cx, cy + 30, text=sub, fill="white", font=("Arial", 13),
                      justify="center", tags="overlay")

    # ---------------------- Bản đồ nhìn từ trên xuống ----------------------
    def draw_preview(self):
        """Vẽ toàn bộ bản đồ: tường, lối ra, quái vật, vị trí + hướng nhìn của bạn."""
        c = self.canvas
        c.delete("all")
        self.view_built = False
        size = VIEW_H
        ox = (VIEW_W - size) / 2
        cs = size / self.n
        c.create_rectangle(0, 0, VIEW_W, VIEW_H, fill=C_DARK, outline="")
        c.create_rectangle(ox, 0, ox + size, size, fill=C_FLOOR, outline="")

        # gộp các đoạn tường liên tiếp trên 1 hàng cho nhẹ
        for y in range(self.n):
            x = 0
            while x < self.n:
                if self.grid[y][x] == 1:
                    x2 = x
                    while x2 + 1 < self.n and self.grid[y][x2 + 1] == 1:
                        x2 += 1
                    c.create_rectangle(ox + x * cs, y * cs, ox + (x2 + 1) * cs, (y + 1) * cs,
                                       fill=C_WALL, outline="")
                    x = x2 + 1
                else:
                    x += 1

        def center(pos):
            return ox + (pos[0] + 0.5) * cs, (pos[1] + 0.5) * cs

        def mark(pos, color, r):
            cx, cy = center(pos)
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=color, outline="white", width=2)

        # quái vật (chấm đỏ) vẽ trước để lối ra và nhân vật nằm đè lên trên
        for m in self.monsters:
            mark((m["x"], m["y"]), C_MONSTER, max(cs * 0.8, 5))
        mark(self.exit, C_EXIT, max(cs * 0.9, 7))
        r = max(cs * 0.9, 7)
        mark((self.px, self.py), C_PLAYER, r)
        cx, cy = center((self.px, self.py))
        fx, fy = FACE[self.facing]
        c.create_line(cx, cy, cx + fx * r * 2.6, cy + fy * r * 2.6, fill="white",
                      width=3, arrow=tk.LAST)

        secs = max(1, int(self.preview_end - time.time()) + 1)
        self.preview_last = secs
        self.set_hud(f"{self.preview_title}  Còn {secs}s\n"
                     f"Xanh dương: bạn (mũi tên = hướng) • Xanh lá: lối ra • Đỏ: quái • Enter: bỏ qua")


if __name__ == "__main__":
    root = tk.Tk()
    Game(root)
    root.mainloop()