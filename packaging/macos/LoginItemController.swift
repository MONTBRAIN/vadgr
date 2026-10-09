import Foundation
import ServiceManagement

let service = SMAppService.agent(plistName: "com.montbrain.vadgr.agent.plist")
let action = CommandLine.arguments.dropFirst().first ?? ""

do {
    switch action {
    case "status":
        switch service.status {
        case .enabled: print("enabled")
        case .requiresApproval: print("requires-approval"); exit(2)
        case .notRegistered: print("disabled"); exit(1)
        case .notFound: print("not-found"); exit(3)
        @unknown default: print("unknown"); exit(4)
        }
    case "enable":
        try service.register()
        if service.status == .requiresApproval {
            SMAppService.openSystemSettingsLoginItems()
            fputs("Vadgr needs approval in Login Items.\n", stderr)
            exit(2)
        }
    case "disable":
        try service.unregister()
    case "open-settings":
        SMAppService.openSystemSettingsLoginItems()
    default:
        fputs("Usage: vadgr-login-item status|enable|disable|open-settings\n", stderr)
        exit(64)
    }
} catch {
    fputs("The Vadgr login item operation failed: \(error.localizedDescription)\n", stderr)
    exit(1)
}
