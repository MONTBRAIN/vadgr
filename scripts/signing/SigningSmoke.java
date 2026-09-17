import com.ssl.code.signing.tool.CodeSignTool;
import com.ssl.code.signing.tool.csc.CscApi;
import com.ssl.code.signing.tool.csc.CredentialInfo;
import com.ssl.code.signing.tool.util.AccessToken;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Base64;
import java.util.LinkedHashSet;
import java.util.Properties;
import java.util.Set;
import javax.security.auth.x500.X500Principal;
import picocli.CommandLine;

/** One file, one signing attempt; credentials never cross an OS argument boundary. */
public final class SigningSmoke {
    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalArgumentException();
        return value;
    }

    private static String digest(X509Certificate certificate, String algorithm) throws Exception {
        StringBuilder text = new StringBuilder();
        for (byte b : MessageDigest.getInstance(algorithm).digest(certificate.getEncoded())) {
            text.append(String.format("%02X", b));
        }
        return text.toString();
    }

    public static void main(String[] args) {
        PrintStream report = System.out;
        PrintStream sink = new PrintStream(OutputStream.nullOutputStream());
        // Vendor failures may contain an HTTP response or authentication material.
        // Suppression starts before vendor classes initialize, not after a failure.
        System.setOut(sink);
        System.setErr(sink);
        System.setIn(InputStream.nullInputStream());
        int result = 70;
        try {
            if (args.length != 1) throw new IllegalArgumentException();
            Path logConfig = Path.of(required("SMOKE_LOG_CONFIG")).toRealPath();
            String config = Files.readString(logConfig);
            if (!config.contains("<Root level=\"OFF\" />") || config.contains("<Appenders")) {
                throw new IllegalArgumentException();
            }
            System.setProperty("log4j.configurationFile", logConfig.toUri().toString());
            System.setProperty("log4j2.disableJmx", "true");
            System.setProperty("org.apache.commons.logging.Log", "org.apache.commons.logging.impl.NoOpLog");
            java.util.logging.LogManager.getLogManager().reset();
            String username = required("ES_USERNAME");
            String password = required("ES_PASSWORD");
            if (args[0].equals("self-test")) {
                System.out.println(username);
                System.err.println(password);
                org.apache.logging.log4j.LogManager.getLogger(SigningSmoke.class).error(required("ES_TOTP_SECRET"));
                if (!new X500Principal("CN=Sample,O=Sample,C=CO").equals(
                    new X500Principal("CN=Sample, O=Sample, C=CO"))) throw new IllegalStateException();
                // This path fails on a missing file before any HTTP call.
                String missing = Path.of("missing-smoke-input.exe").toAbsolutePath().toString();
                if (Files.exists(Path.of(missing))) throw new IllegalArgumentException();
                int code = new CommandLine(new CodeSignTool()).execute("sign",
                    "-username=" + username, "-password=" + password,
                    "-totp_secret=" + required("ES_TOTP_SECRET"),
                    "-input_file_path=" + missing, "-override=true");
                if (code != 3 || Files.exists(Path.of("logs"))) throw new IllegalStateException();
                report.println("Dummy credential suppression: PASS; vendor missing-file refusal verified.");
                result = 0;
            } else {
                if (!args[0].equals("inspect") && !args[0].equals("sign")) {
                    throw new IllegalArgumentException();
                }
                Properties settings = new Properties();
                try (InputStream input = Files.newInputStream(Path.of("conf", "code_sign_tool.properties"))) {
                    settings.load(input);
                }
                if (!"https://login.ssl.com/oauth2/token".equals(settings.getProperty("OAUTH2_ENDPOINT"))
                    || !"https://cs.ssl.com".equals(settings.getProperty("CSC_API_ENDPOINT"))) {
                    throw new IllegalArgumentException();
                }
                String token = new AccessToken(settings.getProperty("CLIENT_ID"), username,
                    password, settings.getProperty("OAUTH2_ENDPOINT")).getAccessToken();
                CscApi api = new CscApi(token, settings.getProperty("CSC_API_ENDPOINT"));
                // These are the same two credential classes the pinned vendor sign command lists.
                Set<String> identifiers = new LinkedHashSet<>();
                identifiers.addAll(Arrays.asList(api.getCredentialIDs("EVCS")));
                identifiers.addAll(Arrays.asList(api.getCredentialIDs("OVCS")));
                if (identifiers.isEmpty()) throw new IllegalStateException();
                String selected = null;
                String expected = args[0].equals("sign") ? required("EXPECTED_CERT_SHA256") : "";
                if (args[0].equals("sign") && !expected.matches("[A-Fa-f0-9]{64}")) {
                    throw new IllegalArgumentException();
                }
                for (String identifier : identifiers) {
                    CredentialInfo info = api.getCredentialInfo(identifier);
                    X509Certificate certificate = info.getCerts().get(0);
                    certificate.checkValidity();
                    if (!certificate.getExtendedKeyUsage().contains("1.3.6.1.5.5.7.3.3")) {
                        throw new IllegalStateException();
                    }
                    String fingerprint = digest(certificate, "SHA-256");
                    if (args[0].equals("inspect")) {
                        report.println("Public certificate subject: " + certificate.getSubjectX500Principal().getName());
                        report.println("Public certificate issuer: " + certificate.getIssuerX500Principal().getName());
                        report.println("Public certificate validity: " + certificate.getNotBefore().toInstant()
                            + " to " + certificate.getNotAfter().toInstant());
                        report.println("Public certificate SHA256: " + fingerprint);
                        report.println("Public certificate SHA1: " + digest(certificate, "SHA-1"));
                    } else if (fingerprint.equalsIgnoreCase(expected)) {
                        if (selected != null) throw new IllegalStateException();
                        if (!new X500Principal(required("EXPECTED_CERT_SUBJECT")).equals(
                            certificate.getSubjectX500Principal())) throw new IllegalStateException();
                        selected = identifier;
                    }
                }
                if (args[0].equals("inspect")) {
                    report.println("Public certificate inspection complete. Signatures requested: 0.");
                    result = 0;
                } else {
                    if (selected == null || api.isOtpTypeOnline(selected)) throw new IllegalStateException();
                    String seed = required("ES_TOTP_SECRET");
                    byte[] decoded = Base64.getDecoder().decode(seed);
                    if (decoded.length < 16 || decoded.length > 64) throw new IllegalArgumentException();
                    Arrays.fill(decoded, (byte) 0);
                    Path input = Path.of("smoke-input.exe").toRealPath();
                    if (Files.size(input) > 1048576) throw new IllegalArgumentException();
                    // Picocli receives Java strings in-process. No vendor batch file or child process runs.
                    int code = new CommandLine(new CodeSignTool()).execute("sign",
                        "-username=" + username, "-password=" + password,
                        "-credential_id=" + selected, "-totp_secret=" + seed,
                        "-input_file_path=" + input, "-output_dir_path=" + Path.of("signed").toRealPath(),
                        "-malware_block=true");
                    report.println("Vendor signing exit code: " + code + ". No retry performed.");
                    result = code == 0 ? 0 : 71;
                }
            }
        } catch (Throwable failure) {
            // Never print exception text, causes, HTTP bodies, or a stack trace.
            report.println("Signing probe stopped. Authentication, certificate, configuration or vendor check failed. No retry performed.");
        }
        System.exit(result);
    }
}
