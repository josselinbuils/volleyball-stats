// The Mac app: the app's page in a window of its own, its Dock icon, the server's life its own. It starts the server
// (`stats server --with-app`) with a pipe on its stdin: the server stops once that pipe ends, when this app quits.
// Closing the window hides it, the Dock icon shows it again. Not installed yet (the .dmg's first open), it runs
// install.sh in a Terminal window, which opens it again once done. Built by app.sh.

import AppKit
import WebKit

let french = (Locale.preferredLanguages.first ?? "").hasPrefix("fr")
func tr(_ fr: String, _ en: String) -> String { french ? fr : en }

let home = FileManager.default.homeDirectoryForCurrentUser
// shortcut.py writes the launcher's path; the .dmg's app, before the install, has none.
let launcher = (Bundle.main.object(forInfoDictionaryKey: "VSLauncher") as? String) ?? home.appendingPathComponent(".local/bin/volleyball-stats").path
let base = URL(string: "http://127.0.0.1:8765/")!
let log = home.appendingPathComponent("Library/Logs/Volleyball Stats.log")

func quoted(_ text: String) -> String { "'" + text.replacingOccurrences(of: "'", with: "'\\''") + "'" }

func escaped(_ text: String) -> String {
    text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
}

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var checkedAt = Date.distantPast
    // The app's page asked for (else the placeholder shows), a server check under way, the downloads' files.
    var onPage = false
    var checking = false
    var failed = false
    var quitting = false
    var title: NSKeyValueObservation?
    var files: [ObjectIdentifier: URL] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard FileManager.default.isExecutableFile(atPath: launcher) else {
            return install()
        }
        menu()
        open()
        placeholder()
        start()
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in self?.tick() }
    }

    /// The server started, unless it runs: its output in the log, for when it fails before its own log.
    func start() {
        if server?.isRunning == true {
            return
        }
        failed = false
        let process = Process()
        process.executableURL = URL(fileURLWithPath: launcher)
        process.arguments = ["server", "--with-app"]
        process.standardInput = Pipe()
        FileManager.default.createFile(atPath: log.path, contents: nil)
        let output = try? FileHandle(forWritingTo: log)
        process.standardOutput = output ?? FileHandle.nullDevice
        process.standardError = output ?? FileHandle.nullDevice
        do {
            try process.run()
            server = process
        } catch {
            fail()
        }
    }

    /// Every half second until the page shows, then every 5 s: the page once the server answers; the server started again
    /// when it is gone (stopped from a terminal, or another one that answered stopped), the failure shown when it ended
    /// without answering.
    func tick() {
        if checking || failed || quitting || (onPage && Date().timeIntervalSince(checkedAt) < 5) {
            return
        }
        checking = true
        checkedAt = Date()
        var request = URLRequest(url: base.appendingPathComponent("current"))
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            let answers = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async {
                guard let self else { return }
                self.checking = false
                if answers {
                    if !self.onPage {
                        self.onPage = true
                        self.web.load(URLRequest(url: base))
                    }
                    return
                }
                if self.server?.isRunning == true {
                    return
                }
                if let ended = self.server, ended.terminationStatus != 0 {
                    return self.fail()
                }
                if self.onPage {
                    self.onPage = false
                    self.placeholder()
                }
                self.start()
            }
        }.resume()
    }

    func fail() {
        failed = true
        onPage = false
        let lines = ((try? String(contentsOf: log, encoding: .utf8)) ?? "").split(separator: "\n").suffix(12).joined(separator: "\n")
        placeholder(failure: lines)
    }

    /// The page while the server starts, or what stopped it with a button to try again.
    func placeholder(failure: String? = nil) {
        let body: String
        if let failure {
            body = """
            <p class="error">\(tr("Volleyball Stats n'a pas pu démarrer.", "Volleyball Stats could not start."))</p>
            <a class="button" href="vs-retry:">\(tr("Réessayer", "Try again"))</a>
            \(failure.isEmpty ? "" : "<pre>\(escaped(failure))</pre>")
            """
        } else {
            body = "<div class=\"spinner\"></div><p>\(tr("Ouverture…", "Opening…"))</p>"
        }
        web.loadHTMLString("""
        <!doctype html><html><head><meta charset="utf-8"><style>
        :root { color-scheme: light dark; }
        body { margin: 0; height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center;
          gap: 16px; font: 14px -apple-system, sans-serif; background: Canvas; color: CanvasText; }
        p { margin: 0; opacity: .7; } .error { opacity: 1; color: #d0342c; }
        .spinner { width: 24px; height: 24px; border: 3px solid color-mix(in srgb, CanvasText 15%, transparent);
          border-top-color: color-mix(in srgb, CanvasText 60%, transparent); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .button { padding: 6px 14px; border-radius: 8px; border: 1px solid color-mix(in srgb, CanvasText 20%, transparent);
          color: inherit; text-decoration: none; }
        pre { max-width: 90vw; overflow: auto; font-size: 11px; opacity: .6; white-space: pre-wrap; }
        </style></head><body>\(body)</body></html>
        """, baseURL: nil)
    }

    func open() {
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        if #available(macOS 12.3, *) {
            config.preferences.isElementFullscreenEnabled = true
        }
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        if #available(macOS 13.3, *) {
            web.isInspectable = true
        }
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Volleyball Stats"
        window.contentView = web
        window.delegate = self
        window.minSize = NSSize(width: 360, height: 480)
        window.tabbingMode = .disallowed
        window.isReleasedWhenClosed = false
        window.center()
        window.setFrameAutosaveName("Volleyball Stats")
        title = web.observe(\.title) { [weak self] web, _ in
            self?.window.title = (web.title?.isEmpty == false ? web.title : nil) ?? "Volleyball Stats"
        }
        show()
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func retry() {
        placeholder()
        start()
    }

    @objc func reload() {
        if onPage {
            web.reload()
        }
    }

    // Closing the window hides the app, as on a Mac; the Dock icon brings it back.
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.orderOut(nil)
        return false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if window != nil {
            show()
        }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    /// The page left first, for its last saves to go (they go on leaving), then the app quits: the server's pipe ends.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard onPage, !quitting else {
            return .terminateNow
        }
        quitting = true
        web.load(URLRequest(url: URL(string: "about:blank")!))
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { NSApp.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }

    func external(_ url: URL) -> Bool {
        ["http", "https"].contains(url.scheme ?? "") && (url.host != base.host || url.port != base.port)
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else {
            return decisionHandler(.allow)
        }
        if url.scheme == "vs-retry" {
            retry()
            return decisionHandler(.cancel)
        }
        if action.shouldPerformDownload {
            return decisionHandler(.download)
        }
        if action.targetFrame?.isMainFrame != false && external(url) {
            NSWorkspace.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        decisionHandler(!response.canShowMIMEType || disposition.lowercased().hasPrefix("attachment") ? .download : .allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    // The server gone while the page loads: the placeholder until it answers again.
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let error = error as NSError
        if onPage && !quitting && error.domain == NSURLErrorDomain && error.code != NSURLErrorCancelled {
            onPage = false
            placeholder()
        }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }

    /// Downloads go to the Downloads folder, a number added when the name is taken.
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let folder = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        let name = suggestedFilename as NSString
        var target = folder.appendingPathComponent(suggestedFilename)
        var n = 2
        while FileManager.default.fileExists(atPath: target.path) {
            let numbered = "\(name.deletingPathExtension) \(n)" + (name.pathExtension.isEmpty ? "" : ".\(name.pathExtension)")
            target = folder.appendingPathComponent(numbered)
            n += 1
        }
        files[ObjectIdentifier(download)] = target
        completionHandler(target)
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let file = files.removeValue(forKey: ObjectIdentifier(download)) {
            // The Dock's Downloads stack bounces, as for a browser's download.
            DistributedNotificationCenter.default().post(name: Notification.Name("com.apple.DownloadFileFinished"), object: file.path)
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if external(url) {
                NSWorkspace.shared.open(url)
            } else {
                webView.load(action.request)
            }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: tr("Annuler", "Cancel"))
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    /// The .dmg's first open: install.sh in a Terminal window, its steps shown; it opens this app again at the end.
    func install() {
        guard let installer = Bundle.main.url(forResource: "install", withExtension: "sh") else {
            let alert = NSAlert()
            alert.messageText = tr("Volleyball Stats n'est plus installé : téléchargez-le à nouveau.", "Volleyball Stats is no longer installed: download it again.")
            alert.runModal()
            return NSApp.terminate(nil)
        }
        let script = FileManager.default.temporaryDirectory.appendingPathComponent("volleyball-stats-install.command")
        let text = "#!/bin/sh\nVOLLEYBALL_STATS_APP=\(quoted(Bundle.main.bundlePath)) exec /bin/sh \(quoted(installer.path))\n"
        try? text.write(to: script, atomically: true, encoding: .utf8)
        chmod(script.path, 0o755)
        removexattr(script.path, "com.apple.quarantine", 0)
        let terminal = Process()
        terminal.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        terminal.arguments = ["-a", "Terminal", script.path]
        try? terminal.run()
        terminal.waitUntilExit()
        NSApp.terminate(nil)
    }

    func menu() {
        let bar = NSMenu()
        func item(_ title: String, _ action: Selector?, _ key: String = "", _ modifiers: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let made = NSMenuItem(title: title, action: action, keyEquivalent: key)
            made.keyEquivalentModifierMask = modifiers
            return made
        }
        func add(_ title: String, _ items: [NSMenuItem]) -> NSMenu {
            let menu = NSMenu(title: title)
            items.forEach(menu.addItem)
            let holder = NSMenuItem()
            holder.submenu = menu
            bar.addItem(holder)
            return menu
        }
        _ = add("Volleyball Stats", [
            item(tr("À propos de Volleyball Stats", "About Volleyball Stats"), #selector(NSApplication.orderFrontStandardAboutPanel(_:))),
            .separator(),
            item(tr("Masquer Volleyball Stats", "Hide Volleyball Stats"), #selector(NSApplication.hide(_:)), "h"),
            item(tr("Masquer les autres", "Hide Others"), #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item(tr("Tout afficher", "Show All"), #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            item(tr("Quitter Volleyball Stats", "Quit Volleyball Stats"), #selector(NSApplication.terminate(_:)), "q"),
        ])
        _ = add(tr("Édition", "Edit"), [
            item(tr("Annuler", "Undo"), Selector(("undo:")), "z"),
            item(tr("Rétablir", "Redo"), Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item(tr("Couper", "Cut"), #selector(NSText.cut(_:)), "x"),
            item(tr("Copier", "Copy"), #selector(NSText.copy(_:)), "c"),
            item(tr("Coller", "Paste"), #selector(NSText.paste(_:)), "v"),
            item(tr("Tout sélectionner", "Select All"), #selector(NSText.selectAll(_:)), "a"),
        ])
        _ = add(tr("Présentation", "View"), [
            item(tr("Recharger la page", "Reload Page"), #selector(reload), "r"),
            .separator(),
            item(tr("Plein écran", "Full Screen"), #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ])
        NSApp.windowsMenu = add(tr("Fenêtre", "Window"), [
            item(tr("Placer dans le Dock", "Minimize"), #selector(NSWindow.performMiniaturize(_:)), "m"),
            item(tr("Fermer", "Close"), #selector(NSWindow.performClose(_:)), "w"),
        ])
        NSApp.mainMenu = bar
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
