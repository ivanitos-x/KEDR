using System;
using System.IO;
using System.Diagnostics;
using System.Text;
using System.Windows.Forms;
class ViewerLauncher {
    static string Quote(string s) {
        var b = new StringBuilder("\""); int slashes = 0;
        foreach (char c in s) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { b.Append('\\', slashes * 2 + 1); b.Append(c); }
            else { b.Append('\\', slashes); b.Append(c); }
            slashes = 0;
        }
        b.Append('\\', slashes * 2); b.Append('"'); return b.ToString();
    }
    [STAThread] static int Main(string[] args) {
        try {
            string exe = System.Reflection.Assembly.GetExecutingAssembly().Location;
            string root = Path.GetDirectoryName(exe);
            string name = Path.GetFileNameWithoutExtension(exe);
            string mode = name.Equals("KEDR", StringComparison.OrdinalIgnoreCase) ||
                          name.Equals("CLAP PNG Viewer", StringComparison.OrdinalIgnoreCase)
                          ? "png" : "document";
            var command = new StringBuilder(Quote(Path.Combine(root,"launch.py")) + " " + mode);
            bool wait = false;
            bool options = true;
            foreach (string arg in args) {
                if (options && arg == "--wait") {
                    wait = true;
                    continue;
                }
                if (arg == "--") options = false;
                command.Append(" " + Quote(arg));
            }
            var start = new ProcessStartInfo(Path.Combine(root,@".venv\Scripts\pythonw.exe"),command.ToString()) {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true
            };
            using (var child = Process.Start(start)) {
                if (!wait) return 0;
                child.WaitForExit();
                return child.ExitCode;
            }
        } catch (Exception e) {
            MessageBox.Show(e.Message,"CLAP — ошибка запуска");
            return 1;
        }
    }
}
