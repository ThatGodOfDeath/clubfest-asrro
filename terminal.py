import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import csv
import os
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

BAUD_RATE = 9600
CSV_FILE = "registrations.csv"


# ============================================================
# MAIN APPLICATION
# ============================================================

class RFIDTerminal:

    def __init__(self, root):

        self.root = root
        self.root.title("Event RFID Registration Terminal")
        self.root.geometry("900x650")
        self.root.minsize(800, 600)

        self.serial_connection = None
        self.serial_thread = None
        self.running = False

        self.current_rfid = None

        self.setup_csv()
        self.build_interface()
        self.refresh_ports()
        self.update_statistics()

    # ========================================================
    # CSV
    # ========================================================

    def setup_csv(self):

        if not os.path.exists(CSV_FILE):

            with open(
                CSV_FILE,
                "w",
                newline="",
                encoding="utf-8"
            ) as file:

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

        with open(
            CSV_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:

            return list(csv.DictReader(file))

    def append_csv(
        self,
        student_id,
        rfid_id,
        department
    ):

        with open(
            CSV_FILE,
            "a",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.writer(file)

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                student_id,
                rfid_id,
                department,
                "pending"
            ])

    # ========================================================
    # INTERFACE
    # ========================================================

    def build_interface(self):

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header = tk.Frame(
            self.root,
            bg="#172554",
            height=80
        )

        header.pack(
            fill="x"
        )

        tk.Label(
            header,
            text="EVENT REGISTRATION",
            font=("Arial", 24, "bold"),
            fg="white",
            bg="#172554"
        ).pack(
            pady=(15, 0)
        )

        tk.Label(
            header,
            text="RFID PARTICIPANT TERMINAL",
            font=("Arial", 11),
            fg="#bfdbfe",
            bg="#172554"
        ).pack()

        # ----------------------------------------------------
        # MAIN AREA
        # ----------------------------------------------------

        main = tk.Frame(
            self.root,
            bg="#f1f5f9"
        )

        main.pack(
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # CONNECTION PANEL
        # ----------------------------------------------------

        connection = tk.LabelFrame(
            main,
            text=" RFID Scanner ",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9",
            padx=15,
            pady=10
        )

        connection.pack(
            fill="x",
            padx=25,
            pady=(20, 10)
        )

        tk.Label(
            connection,
            text="Serial Port:",
            bg="#f1f5f9",
            font=("Arial", 10)
        ).pack(
            side="left"
        )

        self.port_combo = ttk.Combobox(
            connection,
            width=15,
            state="readonly"
        )

        self.port_combo.pack(
            side="left",
            padx=10
        )

        tk.Button(
            connection,
            text="Refresh",
            command=self.refresh_ports
        ).pack(
            side="left",
            padx=5
        )

        self.connect_button = tk.Button(
            connection,
            text="Connect",
            width=12,
            command=self.toggle_connection
        )

        self.connect_button.pack(
            side="left",
            padx=5
        )

        self.connection_status = tk.Label(
            connection,
            text="● Disconnected",
            fg="red",
            bg="#f1f5f9",
            font=("Arial", 10, "bold")
        )

        self.connection_status.pack(
            side="right"
        )

        # ----------------------------------------------------
        # RFID DISPLAY
        # ----------------------------------------------------

        scanner_frame = tk.Frame(
            main,
            bg="white",
            bd=1,
            relief="solid"
        )

        scanner_frame.pack(
            fill="x",
            padx=25,
            pady=10
        )

        tk.Label(
            scanner_frame,
            text="SCAN STUDENT RFID CARD",
            font=("Arial", 16, "bold"),
            bg="white",
            fg="#172554"
        ).pack(
            pady=(20, 10)
        )

        self.scan_status = tk.Label(
            scanner_frame,
            text="Waiting for RFID card...",
            font=("Arial", 11),
            bg="white",
            fg="#64748b"
        )

        self.scan_status.pack()

        self.rfid_display = tk.Label(
            scanner_frame,
            text="—",
            font=("Consolas", 22, "bold"),
            bg="white",
            fg="#0f172a"
        )

        self.rfid_display.pack(
            pady=15
        )

        # ----------------------------------------------------
        # STUDENT ID
        # ----------------------------------------------------

        student_frame = tk.Frame(
            main,
            bg="#f1f5f9"
        )

        student_frame.pack(
            fill="x",
            padx=25,
            pady=10
        )

        tk.Label(
            student_frame,
            text="Student ID:",
            font=("Arial", 12, "bold"),
            bg="#f1f5f9"
        ).pack(
            side="left"
        )

        self.student_entry = tk.Entry(
            student_frame,
            font=("Arial", 16),
            width=25
        )

        self.student_entry.pack(
            side="left",
            padx=15
        )

        self.student_entry.bind(
            "<Return>",
            lambda event: self.register_student()
        )

        self.register_button = tk.Button(
            student_frame,
            text="REGISTER STUDENT",
            font=("Arial", 11, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            width=20,
            height=2,
            command=self.register_student
        )

        self.register_button.pack(
            side="left"
        )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        self.result_label = tk.Label(
            main,
            text="Scan an RFID card to begin.",
            font=("Arial", 13, "bold"),
            bg="#f1f5f9",
            fg="#64748b"
        )

        self.result_label.pack(
            pady=10
        )

        # ----------------------------------------------------
        # STATISTICS
        # ----------------------------------------------------

        stats = tk.LabelFrame(
            main,
            text=" Registration Statistics ",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9",
            padx=15,
            pady=10
        )

        stats.pack(
            fill="x",
            padx=25,
            pady=10
        )

        self.total_label = tk.Label(
            stats,
            text="Total: 0",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9"
        )

        self.total_label.pack(
            side="left",
            padx=20
        )

        self.synced_label = tk.Label(
            stats,
            text="Synced: 0",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9"
        )

        self.synced_label.pack(
            side="left",
            padx=20
        )

        self.pending_label = tk.Label(
            stats,
            text="Pending: 0",
            font=("Arial", 11, "bold"),
            bg="#f1f5f9"
        )

        self.pending_label.pack(
            side="left",
            padx=20
        )

        # ----------------------------------------------------
        # FOOTER
        # ----------------------------------------------------

        footer = tk.Frame(
            self.root,
            bg="#e2e8f0"
        )

        footer.pack(
            fill="x"
        )

        tk.Label(
            footer,
            text="Local backup: registrations.csv",
            font=("Arial", 9),
            bg="#e2e8f0",
            fg="#475569"
        ).pack(
            pady=6
        )

    # ========================================================
    # SERIAL PORTS
    # ========================================================

    def refresh_ports(self):

        ports = serial.tools.list_ports.comports()

        port_names = [
            port.device
            for port in ports
        ]

        self.port_combo["values"] = port_names

        if port_names:
            self.port_combo.current(0)

    # ========================================================
    # SERIAL CONNECTION
    # ========================================================

    def toggle_connection(self):

        if self.running:
            self.disconnect()
        else:
            self.connect()

    def connect(self):

        port = self.port_combo.get()

        if not port:

            messagebox.showerror(
                "Error",
                "Please select a serial port."
            )

            return

        try:

            self.serial_connection = serial.Serial(
                port,
                BAUD_RATE,
                timeout=1
            )

            self.running = True

            self.connect_button.config(
                text="Disconnect"
            )

            self.connection_status.config(
                text="● Connected",
                fg="green"
            )

            self.scan_status.config(
                text="Waiting for RFID card...",
                fg="#2563eb"
            )

            self.serial_thread = threading.Thread(
                target=self.serial_reader,
                daemon=True
            )

            self.serial_thread.start()

        except Exception as e:

            messagebox.showerror(
                "Connection Error",
                str(e)
            )

    def disconnect(self):

        self.running = False

        if self.serial_connection:

            try:
                self.serial_connection.close()

            except:
                pass

        self.serial_connection = None

        self.connect_button.config(
            text="Connect"
        )

        self.connection_status.config(
            text="● Disconnected",
            fg="red"
        )

        self.scan_status.config(
            text="Scanner disconnected.",
            fg="red"
        )

    # ========================================================
    # SERIAL READER
    # ========================================================

    def serial_reader(self):

        while self.running:

            try:

                line = (
                    self.serial_connection
                    .readline()
                    .decode(
                        "ascii",
                        errors="ignore"
                    )
                    .strip()
                )

                if not line:
                    continue

                # Expected:
                #
                # RFID:024F00BB1B57

                if line.startswith("RFID:"):

                    rfid_id = line[5:].strip()

                    self.root.after(
                        0,
                        self.rfid_detected,
                        rfid_id
                    )

            except Exception:

                if self.running:

                    self.root.after(
                        0,
                        self.disconnect
                    )

                break

    # ========================================================
    # RFID DETECTED
    # ========================================================

    def rfid_detected(self, rfid_id):

        self.current_rfid = rfid_id

        self.rfid_display.config(
            text=rfid_id
        )

        self.scan_status.config(
            text="RFID detected. Enter Student ID.",
            fg="#16a34a"
        )

        self.result_label.config(
            text="Waiting for Student ID...",
            fg="#2563eb"
        )

        self.student_entry.delete(
            0,
            tk.END
        )

        self.student_entry.focus_set()

    # ========================================================
    # STUDENT ID VALIDATION
    # ========================================================

    def validate_student_id(self, student_id):

        if not student_id.isdigit():

            return False

        if len(student_id) != 7:

            return False

        return True

    # ========================================================
    # DEPARTMENT EXTRACTION
    # ========================================================

    def get_department(self, student_id):

        # Example:
        #
        # 2204059
        #   ^^
        #   department code
        #
        # Positions 3 and 4

        return student_id[2:4]

    # ========================================================
    # DUPLICATE CHECK
    # ========================================================

    def student_exists(self, student_id):

        records = self.read_csv()

        for record in records:

            if record["s_id"] == student_id:

                return True

        return False

    def rfid_exists(self, rfid_id):

        records = self.read_csv()

        for record in records:

            if record["r_id"] == rfid_id:

                return True

        return False

    # ========================================================
    # REGISTRATION
    # ========================================================

    def register_student(self):

        if not self.current_rfid:

            messagebox.showwarning(
                "No RFID",
                "Please scan an RFID card first."
            )

            return

        student_id = (
            self.student_entry
            .get()
            .strip()
        )

        if not self.validate_student_id(student_id):

            messagebox.showerror(
                "Invalid Student ID",
                "Student ID must contain exactly 7 digits."
            )

            self.student_entry.focus_set()

            return

        # Duplicate Student ID

        if self.student_exists(student_id):

            messagebox.showerror(
                "Already Registered",
                f"Student ID {student_id} is already registered."
            )

            self.reset_registration()

            return

        # Duplicate RFID

        if self.rfid_exists(self.current_rfid):

            messagebox.showerror(
                "RFID Already Registered",
                f"RFID {self.current_rfid} is already registered."
            )

            self.reset_registration()

            return

        # Department

        department = self.get_department(
            student_id
        )

        # Save CSV

        self.append_csv(
            student_id,
            self.current_rfid,
            department
        )

        # Success

        self.result_label.config(
            text="✓ REGISTRATION SUCCESSFUL",
            fg="#16a34a"
        )

        self.scan_status.config(
            text="Registration saved locally.",
            fg="#16a34a"
        )

        self.update_statistics()

        # Reset after short delay

        self.root.after(
            1500,
            self.reset_registration
        )

    # ========================================================
    # RESET
    # ========================================================

    def reset_registration(self):

        self.current_rfid = None

        self.rfid_display.config(
            text="—"
        )

        self.student_entry.delete(
            0,
            tk.END
        )

        self.scan_status.config(
            text="Waiting for RFID card...",
            fg="#64748b"
        )

        self.result_label.config(
            text="Scan an RFID card to begin.",
            fg="#64748b"
        )

    # ========================================================
    # STATISTICS
    # ========================================================

    def update_statistics(self):

        records = self.read_csv()

        total = len(records)

        synced = sum(
            1
            for record in records
            if record["server_status"] == "synced"
        )

        pending = sum(
            1
            for record in records
            if record["server_status"] == "pending"
        )

        self.total_label.config(
            text=f"Total: {total}"
        )

        self.synced_label.config(
            text=f"Synced: {synced}"
        )

        self.pending_label.config(
            text=f"Pending: {pending}"
        )


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = RFIDTerminal(root)

    root.mainloop()