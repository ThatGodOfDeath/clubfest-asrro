import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import csv
import os
import json
import urllib.request
import urllib.error
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

BAUD_RATE = 9600
CSV_FILE = os.path.join(os.path.dirname(__file__), "registrations.csv")
DEFAULT_CLOUD_SERVER = "https://clubfest-asrro.onrender.com"
DEFAULT_LOCAL_SERVER = "http://localhost:3001"

DEPARTMENTS = {
    "01": "Civil Engineering (CE)",
    "02": "Electrical & Electronic Engineering (EEE)",
    "03": "Mechanical Engineering (ME)",
    "04": "Computer Science & Engineering (CSE)",
    "05": "Urban & Regional Planning (URP)",
    "06": "Architecture (ARCH)",
    "07": "Chemical Engineering (ChE)",
    "08": "Naval Architecture & Marine Engineering (NAME)",
    "09": "Materials & Metallurgical Engineering (MME)",
    "10": "Water Resources Engineering (WRE)",
    "11": "Biomedical Engineering (BME)",
    "12": "Industrial & Production Engineering (IPE)"
}


# ============================================================
# MAIN APPLICATION
# ============================================================

class RFIDTerminal:

    def __init__(self, root):
        self.root = root
        self.root.title("Department Clash 2026 - RFID Registration Terminal")
        self.root.geometry("960x720")
        self.root.minsize(850, 650)

        self.serial_connection = None
        self.serial_thread = None
        self.running = False

        self.current_rfid = None
        self.server_url = os.environ.get("SERVER_URL", DEFAULT_CLOUD_SERVER).rstrip("/")
        self.server_online = False
        self.is_syncing = False

        self.setup_csv()
        self.build_interface()
        self.refresh_ports()
        self.update_statistics()

        # Start periodic background tasks
        self.start_background_monitors()

    # ========================================================
    # CSV STORAGE & MANAGEMENT
    # ========================================================

    def setup_csv(self):
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "timestamp",
                    "s_id",
                    "r_id",
                    "department",
                    "server_status"
                ])

    def read_csv(self):
        if not os.path.exists(CSV_FILE):
            return []
        try:
            with open(CSV_FILE, "r", newline="", encoding="utf-8") as file:
                return list(csv.DictReader(file))
        except Exception as e:
            print(f"Error reading CSV: {e}")
            return []

    def append_csv(self, student_id, rfid_id, department, status="pending"):
        try:
            with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    student_id,
                    rfid_id,
                    department,
                    status
                ])
        except Exception as e:
            print(f"Error appending CSV: {e}")

    def update_csv_status(self, student_id, rfid_id, new_status):
        records = self.read_csv()
        updated = False
        for rec in records:
            if rec.get("s_id") == student_id and rec.get("r_id") == rfid_id:
                rec["server_status"] = new_status
                updated = True

        if updated:
            try:
                with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow(["timestamp", "s_id", "r_id", "department", "server_status"])
                    for r in records:
                        writer.writerow([
                            r.get("timestamp", ""),
                            r.get("s_id", ""),
                            r.get("r_id", ""),
                            r.get("department", ""),
                            r.get("server_status", "pending")
                        ])
            except Exception as e:
                print(f"Error updating CSV status: {e}")

    # ========================================================
    # BACKEND API COMMUNICATION (Zero external dependencies)
    # ========================================================

    def ping_server(self):
        url = f"{self.server_url}/health"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RFID-Terminal/1.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return data.get("status") == "ok"
        except Exception:
            pass
        return False

    def send_registration_to_server(self, student_id, rfid_id):
        """Sends POST /api/auth/register to backend with studentId and rfid."""
        url = f"{self.server_url}/api/auth/register"
        payload = json.dumps({"studentId": student_id, "rfid": rfid_id}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RFID-Terminal/1.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=6) as response:
                result = json.loads(response.read().decode("utf-8"))
                return True, result
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
                return False, err_data.get("message", f"HTTP Error {e.code}")
            except Exception:
                return False, f"HTTP Error {e.code}"
        except Exception as e:
            return False, f"Connection Failed: {str(e)}"

    def lookup_rfid_on_server(self, rfid_id):
        """Queries GET /api/player/rfid/:rfid to check if card is already registered."""
        url = f"{self.server_url}/api/player/rfid/{rfid_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RFID-Terminal/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    if data.get("success") and data.get("player"):
                        return data["player"]
        except Exception:
            pass
        return None

    # ========================================================
    # BACKGROUND MONITORING & AUTO-SYNC
    # ========================================================

    def start_background_monitors(self):
        def monitor_loop():
            # Initial check
            self.check_server_health_async()

            # Schedule periodic loop
            self.root.after(10000, self.periodic_worker)

        threading.Thread(target=monitor_loop, daemon=True).start()

    def periodic_worker(self):
        # Health check
        threading.Thread(target=self.check_server_health_async, daemon=True).start()

        # If online, auto-sync pending records
        if self.server_online and not self.is_syncing:
            threading.Thread(target=self.sync_pending_records, daemon=True).start()

        # Re-schedule in 12 seconds
        self.root.after(12000, self.periodic_worker)

    def check_server_health_async(self):
        is_up = self.ping_server()
        self.server_online = is_up

        def update_ui():
            if is_up:
                server_display = self.server_url.replace("https://", "").replace("http://", "")
                self.server_status_badge.config(
                    text=f"● Online ({server_display})",
                    fg="#16a34a"
                )
            else:
                self.server_status_badge.config(
                    text="● Offline (Will save locally)",
                    fg="#dc2626"
                )

        self.root.after(0, update_ui)

    def sync_pending_records(self, manual=False):
        if self.is_syncing:
            return
        self.is_syncing = True

        def run_sync():
            records = self.read_csv()
            pending_list = [r for r in records if r.get("server_status") == "pending"]

            if not pending_list:
                self.is_syncing = False
                if manual:
                    self.root.after(0, lambda: messagebox.showinfo("Sync", "All records are already synced!"))
                return

            synced_count = 0
            for record in pending_list:
                s_id = record.get("s_id")
                r_id = record.get("r_id")
                if s_id and r_id:
                    success, _ = self.send_registration_to_server(s_id, r_id)
                    if success:
                        self.update_csv_status(s_id, r_id, "synced")
                        synced_count += 1

            self.is_syncing = False
            self.root.after(0, self.update_statistics)

            if manual:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Sync Complete",
                    f"Successfully synced {synced_count} of {len(pending_list)} pending records!"
                ))

        threading.Thread(target=run_sync, daemon=True).start()

    # ========================================================
    # INTERFACE
    # ========================================================

    def build_interface(self):

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------
        header = tk.Frame(self.root, bg="#172554", height=90)
        header.pack(fill="x")

        title_frame = tk.Frame(header, bg="#172554")
        title_frame.pack(fill="x", padx=25, pady=(12, 10))

        left_header = tk.Frame(title_frame, bg="#172554")
        left_header.pack(side="left")

        tk.Label(
            left_header,
            text="DEPARTMENT CLASH 2026",
            font=("Arial", 20, "bold"),
            fg="#F9D342",
            bg="#172554"
        ).pack(anchor="w")

        tk.Label(
            left_header,
            text="🎟️ RFID Fast Registration & Booth Authorization Terminal",
            font=("Arial", 11),
            fg="#bfdbfe",
            bg="#172554"
        ).pack(anchor="w")

        # Server Selector in Header
        right_header = tk.Frame(title_frame, bg="#172554")
        right_header.pack(side="right")

        tk.Label(
            right_header,
            text="Backend Target:",
            font=("Arial", 9, "bold"),
            fg="#93c5fd",
            bg="#172554"
        ).pack(anchor="e")

        server_select_frame = tk.Frame(right_header, bg="#172554")
        server_select_frame.pack(anchor="e", pady=2)

        self.server_combo = ttk.Combobox(
            server_select_frame,
            values=["Cloud (Render)", "Local (localhost:3001)"],
            width=18,
            state="readonly"
        )
        self.server_combo.set("Cloud (Render)")
        self.server_combo.pack(side="left", padx=4)
        self.server_combo.bind("<<ComboboxSelected>>", self.on_server_target_change)

        self.server_status_badge = tk.Label(
            right_header,
            text="● Checking Server...",
            font=("Arial", 9, "bold"),
            fg="#fbbf24",
            bg="#172554"
        )
        self.server_status_badge.pack(anchor="e")

        # ----------------------------------------------------
        # MAIN AREA
        # ----------------------------------------------------
        main = tk.Frame(self.root, bg="#f1f5f9")
        main.pack(fill="both", expand=True)

        # ----------------------------------------------------
        # CONNECTION PANEL
        # ----------------------------------------------------
        connection = tk.LabelFrame(
            main,
            text=" 🔌 RFID Scanner Serial Port ",
            font=("Arial", 10, "bold"),
            bg="#f1f5f9",
            padx=15,
            pady=8
        )
        connection.pack(fill="x", padx=25, pady=(12, 8))

        tk.Label(
            connection,
            text="Port:",
            bg="#f1f5f9",
            font=("Arial", 10)
        ).pack(side="left")

        self.port_combo = ttk.Combobox(
            connection,
            width=14,
            state="readonly"
        )
        self.port_combo.pack(side="left", padx=8)

        tk.Button(
            connection,
            text="🔄 Refresh",
            font=("Arial", 9),
            command=self.refresh_ports
        ).pack(side="left", padx=4)

        self.connect_button = tk.Button(
            connection,
            text="Connect",
            font=("Arial", 9, "bold"),
            bg="#2563eb",
            fg="white",
            width=12,
            command=self.toggle_connection
        )
        self.connect_button.pack(side="left", padx=6)

        self.connection_status = tk.Label(
            connection,
            text="● Disconnected",
            fg="#dc2626",
            bg="#f1f5f9",
            font=("Arial", 10, "bold")
        )
        self.connection_status.pack(side="right")

        # ----------------------------------------------------
        # RFID DISPLAY
        # ----------------------------------------------------
        scanner_frame = tk.Frame(main, bg="white", bd=2, relief="solid")
        scanner_frame.pack(fill="x", padx=25, pady=8)

        tk.Label(
            scanner_frame,
            text="SCAN PARTICIPANT RFID CARD",
            font=("Arial", 14, "bold"),
            bg="white",
            fg="#172554"
        ).pack(pady=(12, 4))

        self.scan_status = tk.Label(
            scanner_frame,
            text="Please hold card near scanner...",
            font=("Arial", 10),
            bg="white",
            fg="#64748b"
        )
        self.scan_status.pack()

        self.rfid_display = tk.Label(
            scanner_frame,
            text="—",
            font=("Consolas", 20, "bold"),
            bg="white",
            fg="#0f172a"
        )
        self.rfid_display.pack(pady=8)

        # ----------------------------------------------------
        # STUDENT ID & REGISTRATION
        # ----------------------------------------------------
        student_frame = tk.Frame(main, bg="#f1f5f9")
        student_frame.pack(fill="x", padx=25, pady=8)

        input_box = tk.Frame(student_frame, bg="#f1f5f9")
        input_box.pack(fill="x")

        tk.Label(
            input_box,
            text="Student ID:",
            font=("Arial", 12, "bold"),
            bg="#f1f5f9"
        ).pack(side="left")

        self.student_entry = tk.Entry(
            input_box,
            font=("Consolas", 18, "bold"),
            width=18,
            justify="center"
        )
        self.student_entry.pack(side="left", padx=12)
        self.student_entry.bind("<KeyRelease>", self.on_id_keyrelease)
        self.student_entry.bind("<Return>", lambda event: self.register_student())

        self.register_button = tk.Button(
            input_box,
            text="✅ REGISTER & AUTHORIZE",
            font=("Arial", 11, "bold"),
            bg="#16a34a",
            fg="white",
            activebackground="#15803d",
            activeforeground="white",
            padx=15,
            pady=8,
            command=self.register_student
        )
        self.register_button.pack(side="left", padx=8)

        # Live Department Preview
        self.dept_preview_label = tk.Label(
            student_frame,
            text="",
            font=("Arial", 10, "bold"),
            bg="#f1f5f9",
            fg="#1e40af"
        )
        self.dept_preview_label.pack(anchor="w", padx=(95, 0), pady=(4, 0))

        # ----------------------------------------------------
        # RESULT FEEDBACK
        # ----------------------------------------------------
        self.result_label = tk.Label(
            main,
            text="Scan an RFID card to begin registration.",
            font=("Arial", 12, "bold"),
            bg="#f1f5f9",
            fg="#64748b"
        )
        self.result_label.pack(pady=8)

        # ----------------------------------------------------
        # STATISTICS & SYNC CONTROLS
        # ----------------------------------------------------
        stats = tk.LabelFrame(
            main,
            text=" 📊 Live Registration & Sync Metrics ",
            font=("Arial", 10, "bold"),
            bg="#f1f5f9",
            padx=15,
            pady=8
        )
        stats.pack(fill="x", padx=25, pady=8)

        self.total_label = tk.Label(
            stats,
            text="Total: 0",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9",
            fg="#0f172a"
        )
        self.total_label.pack(side="left", padx=15)

        self.synced_label = tk.Label(
            stats,
            text="Synced: 0",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9",
            fg="#16a34a"
        )
        self.synced_label.pack(side="left", padx=15)

        self.pending_label = tk.Label(
            stats,
            text="Pending: 0",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9",
            fg="#ea580c"
        )
        self.pending_label.pack(side="left", padx=15)

        self.sync_button = tk.Button(
            stats,
            text="🔄 Sync Pending Now",
            font=("Arial", 9, "bold"),
            bg="#e0e7ff",
            fg="#3730a3",
            padx=10,
            command=lambda: self.sync_pending_records(manual=True)
        )
        self.sync_button.pack(side="right", padx=10)

        # ----------------------------------------------------
        # FOOTER
        # ----------------------------------------------------
        footer = tk.Frame(self.root, bg="#e2e8f0", height=30)
        footer.pack(fill="x", side="bottom")

        tk.Label(
            footer,
            text=f"Local Backup: {CSV_FILE}  •  Auto-syncs with backend when connected",
            font=("Arial", 9),
            bg="#e2e8f0",
            fg="#475569"
        ).pack(pady=4)

    # ========================================================
    # EVENT HANDLERS
    # ========================================================

    def on_server_target_change(self, event=None):
        choice = self.server_combo.get()
        if choice == "Cloud (Render)":
            self.server_url = DEFAULT_CLOUD_SERVER
        else:
            self.server_url = DEFAULT_LOCAL_SERVER

        self.server_status_badge.config(text="● Checking...", fg="#fbbf24")
        threading.Thread(target=self.check_server_health_async, daemon=True).start()

    def on_id_keyrelease(self, event=None):
        val = self.student_entry.get().strip()
        if len(val) >= 4 and val[:2].isdigit():
            dept_code = val[2:4]
            dept_name = DEPARTMENTS.get(dept_code)
            if dept_name:
                self.dept_preview_label.config(
                    text=f"🏛️ Department: {dept_name} (Batch '{val[:2]})",
                    fg="#15803d"
                )
            else:
                self.dept_preview_label.config(
                    text=f"⚠️ Unknown Department Code: {dept_code}",
                    fg="#dc2626"
                )
        else:
            self.dept_preview_label.config(text="")

    # ========================================================
    # SERIAL PORTS & CONNECTION
    # ========================================================

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]
        self.port_combo["values"] = port_names

        if port_names:
            self.port_combo.current(0)

    def toggle_connection(self):
        if self.running:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_combo.get()
        if not port:
            messagebox.showerror("Error", "Please select a serial port.")
            return

        try:
            self.serial_connection = serial.Serial(port, BAUD_RATE, timeout=1)
            self.running = True

            self.connect_button.config(text="Disconnect", bg="#dc2626")
            self.connection_status.config(text="● Connected", fg="#16a34a")
            self.scan_status.config(text="Scanner active. Waiting for RFID card...", fg="#2563eb")

            self.serial_thread = threading.Thread(target=self.serial_reader, daemon=True)
            self.serial_thread.start()

        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def disconnect(self):
        self.running = False
        if self.serial_connection:
            try:
                self.serial_connection.close()
            except Exception:
                pass

        self.serial_connection = None
        self.connect_button.config(text="Connect", bg="#2563eb")
        self.connection_status.config(text="● Disconnected", fg="#dc2626")
        self.scan_status.config(text="Scanner disconnected.", fg="#dc2626")

    # ========================================================
    # SERIAL READER & RFID PROCESSING
    # ========================================================

    def serial_reader(self):
        while self.running:
            try:
                line = self.serial_connection.readline().decode("ascii", errors="ignore").strip()
                if not line:
                    continue

                if line.startswith("RFID:"):
                    rfid_id = line[5:].strip()
                    self.root.after(0, self.rfid_detected, rfid_id)

            except Exception:
                if self.running:
                    self.root.after(0, self.disconnect)
                break

    def rfid_detected(self, rfid_id):
        self.current_rfid = rfid_id
        self.rfid_display.config(text=rfid_id)

        # Check local records
        records = self.read_csv()
        existing_local = next((r for r in records if r.get("r_id") == rfid_id), None)

        if existing_local:
            s_id = existing_local.get("s_id")
            dept = existing_local.get("department")
            self.scan_status.config(
                text=f"Card already assigned locally to Student {s_id} ({dept})",
                fg="#16a34a"
            )
            self.result_label.config(
                text=f"ℹ️ Card already registered for Student ID: {s_id}",
                fg="#1e40af"
            )
            self.student_entry.delete(0, tk.END)
            self.student_entry.insert(0, s_id)
            self.on_id_keyrelease()
            return

        # Check server asynchronously
        def check_server_rfid():
            player = self.lookup_rfid_on_server(rfid_id)
            if player:
                def on_found():
                    s_id = player.get("studentId")
                    dept = player.get("deptCode")
                    self.scan_status.config(
                        text=f"Card already registered on Server for Student {s_id} ({dept})",
                        fg="#16a34a"
                    )
                    self.result_label.config(
                        text=f"ℹ️ Verified on Server: Student ID {s_id}",
                        fg="#1e40af"
                    )
                    self.student_entry.delete(0, tk.END)
                    self.student_entry.insert(0, s_id)
                    self.on_id_keyrelease()

                self.root.after(0, on_found)

        threading.Thread(target=check_server_rfid, daemon=True).start()

        # Prompt for entry
        self.scan_status.config(
            text="RFID detected! Enter Student ID and press Register.",
            fg="#16a34a"
        )
        self.result_label.config(
            text="Waiting for Student ID...",
            fg="#2563eb"
        )
        self.student_entry.delete(0, tk.END)
        self.student_entry.focus_set()

    # ========================================================
    # REGISTRATION
    # ========================================================

    def validate_student_id(self, student_id):
        if not student_id.isdigit():
            return False, "Student ID must only contain numbers."
        if len(student_id) < 6 or len(student_id) > 7:
            return False, "Student ID should be 6 or 7 digits (e.g. 2204055)."
        dept_code = student_id[2:4]
        if dept_code not in DEPARTMENTS:
            return False, f"Invalid Department code '{dept_code}' in Student ID."
        return True, ""

    def register_student(self):
        if not self.current_rfid:
            messagebox.showwarning("No RFID Card", "Please scan an RFID card before registering.")
            return

        student_id = self.student_entry.get().strip()
        is_valid, err_msg = self.validate_student_id(student_id)

        if not is_valid:
            messagebox.showerror("Invalid Student ID", err_msg)
            self.student_entry.focus_set()
            return

        # Check duplicate student ID in CSV
        records = self.read_csv()
        if any(r.get("s_id") == student_id for r in records):
            if not messagebox.askyesno(
                "Duplicate ID Warning",
                f"Student ID {student_id} is already in the local registry.\nDo you want to re-authorize and update card assignment?"
            ):
                return

        dept_code = student_id[2:4]
        dept_info = DEPARTMENTS.get(dept_code, dept_code)
        rfid_id = self.current_rfid

        # 1. Save to local CSV immediately
        self.append_csv(student_id, rfid_id, dept_code, "pending")
        self.update_statistics()

        self.result_label.config(
            text=f"🔄 Authorizing {student_id} on server...",
            fg="#d97706"
        )
        self.scan_status.config(
            text="Syncing with Department Clash server...",
            fg="#d97706"
        )

        # 2. Asynchronously sync to Backend
        def sync_worker():
            success, res = self.send_registration_to_server(student_id, rfid_id)

            def on_sync_done():
                if success:
                    self.update_csv_status(student_id, rfid_id, "synced")
                    self.result_label.config(
                        text=f"✅ {student_id} ({dept_info}) AUTHORIZED & SYNCED!",
                        fg="#16a34a"
                    )
                    self.scan_status.config(
                        text="✓ Real-time update broadcasted to arena screens.",
                        fg="#16a34a"
                    )
                else:
                    self.result_label.config(
                        text=f"💾 Saved locally as pending (Server offline/unreachable)",
                        fg="#ea580c"
                    )
                    self.scan_status.config(
                        text="⚠️ Registration saved locally. Will auto-sync when connection is restored.",
                        fg="#ea580c"
                    )

                self.update_statistics()
                self.root.after(2000, self.reset_registration)

            self.root.after(0, on_sync_done)

        threading.Thread(target=sync_worker, daemon=True).start()

    # ========================================================
    # RESET & STATISTICS
    # ========================================================

    def reset_registration(self):
        self.current_rfid = None
        self.rfid_display.config(text="—")
        self.student_entry.delete(0, tk.END)
        self.dept_preview_label.config(text="")
        self.scan_status.config(
            text="Please hold card near scanner...",
            fg="#64748b"
        )
        self.result_label.config(
            text="Scan an RFID card to begin registration.",
            fg="#64748b"
        )

    def update_statistics(self):
        records = self.read_csv()
        total = len(records)
        synced = sum(1 for r in records if r.get("server_status") == "synced")
        pending = sum(1 for r in records if r.get("server_status") == "pending")

        self.total_label.config(text=f"Total: {total}")
        self.synced_label.config(text=f"Synced: {synced}")
        self.pending_label.config(text=f"Pending: {pending}")


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = RFIDTerminal(root)
    root.mainloop()