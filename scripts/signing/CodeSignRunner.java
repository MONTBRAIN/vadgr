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
import java.util.List;
import java.util.Properties;
import java.util.Set;
import java.util.stream.Stream;
import javax.security.auth.x500.X500Principal;
import picocli.CommandLine;
import net.jsign.Signable;
import net.jsign.asn1.authenticode.AuthenticodeObjectIdentifiers;
import org.bouncycastle.asn1.cms.Attribute;
import org.bouncycastle.asn1.cms.ContentInfo;
import org.bouncycastle.cms.CMSSignedData;
import org.bouncycastle.cms.SignerInformation;
import org.bouncycastle.tsp.TimeStampToken;

/** One file, one signing attempt; credentials never cross an OS argument boundary. */
public final class CodeSignRunner {
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
        // The pinned vendor runtime defaults to 32, below Microsoft's nested
        // Authenticode construction depth. Keep the increase bounded.
        System.setProperty("org.bouncycastle.asn1.max_cons_depth", "64");
        int result = 70;
        String failureStage = "startup";
        try {
            if (args.length != 1) throw new IllegalArgumentException();
            Path logConfig = Path.of(required("SIGNING_LOG_CONFIG")).toRealPath();
            String config = Files.readString(logConfig);
            if (!config.contains("<Root level=\"OFF\" />") || config.contains("<Appenders")) {
                throw new IllegalArgumentException();
            }
            System.setProperty("log4j.configurationFile", logConfig.toUri().toString());
            System.setProperty("log4j2.disableJmx", "true");
            System.setProperty("org.apache.commons.logging.Log", "org.apache.commons.logging.impl.NoOpLog");
            java.util.logging.LogManager.getLogManager().reset();
            if (args[0].equals("verify-metadata")) {
                try (Signable file = Signable.of(Path.of(required("SIGNING_INPUT")).toFile())) {
                    List<CMSSignedData> signatures = file.getSignatures();
                    String trustClass = required("SIGNING_TRUST_CLASS");
                    report.println("Embedded signature count: " + signatures.size());
                    if ((trustClass.equals("publisher-sign") && signatures.size() != 1)
                        || (trustClass.equals("vendor-preserve") && signatures.isEmpty())
                        || (!trustClass.equals("publisher-sign") && !trustClass.equals("vendor-preserve"))) {
                        throw new IllegalStateException();
                    }
                    for (int index = 0; index < signatures.size(); index++) {
                        CMSSignedData signature = signatures.get(index);
                        if (signature.getSignerInfos().size() != 1) throw new IllegalStateException();
                        SignerInformation signer = signature.getSignerInfos().getSigners().iterator().next();
                        report.println("Signature " + index + " digest OID: " + signer.getDigestAlgOID());
                        if (!"2.16.840.1.101.3.4.2.1".equals(signer.getDigestAlgOID())) throw new IllegalStateException();
                        Attribute timestamp = signer.getUnsignedAttributes().get(
                            AuthenticodeObjectIdentifiers.SPC_RFC3161_OBJID);
                        report.println("Signature " + index + " RFC3161 timestamp present: " + (timestamp != null));
                        if (timestamp == null || timestamp.getAttrValues().size() != 1) throw new IllegalStateException();
                        TimeStampToken token = new TimeStampToken(new CMSSignedData(
                            ContentInfo.getInstance(timestamp.getAttrValues().getObjectAt(0))));
                        report.println("Signature " + index + " timestamp digest OID: "
                            + token.getTimeStampInfo().getMessageImprintAlgOID().getId());
                        if (!"2.16.840.1.101.3.4.2.1".equals(token.getTimeStampInfo().getMessageImprintAlgOID().getId())
                            || !MessageDigest.isEqual(token.getTimeStampInfo().getMessageImprintDigest(),
                                MessageDigest.getInstance("SHA-256").digest(signer.getSignature()))) {
                            throw new IllegalStateException();
                        }
                    }
                }
                report.println("All SHA256 signatures and bound RFC3161 SHA256 timestamp metadata verified.");
                System.exit(0);
            }
            String username = required("ES_USERNAME");
            String password = required("ES_PASSWORD");
            if (args[0].equals("self-test")) {
                System.out.println(username);
                System.err.println(password);
                org.apache.logging.log4j.LogManager.getLogger(CodeSignRunner.class).error(required("ES_TOTP_SECRET"));
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
                    || !"https://cs.ssl.com".equals(settings.getProperty("CSC_API_ENDPOINT"))
                    || !"http://ts.ssl.com".equals(settings.getProperty("TSA_URL"))) {
                    throw new IllegalArgumentException();
                }
                failureStage = "authentication";
                String token = new AccessToken(settings.getProperty("CLIENT_ID"), username,
                    password, settings.getProperty("OAUTH2_ENDPOINT")).getAccessToken();
                failureStage = "credential-list";
                CscApi api = new CscApi(token, settings.getProperty("CSC_API_ENDPOINT"));
                // These are the same two credential classes the pinned vendor sign command lists.
                Set<String> identifiers = new LinkedHashSet<>();
                identifiers.addAll(Arrays.asList(api.getCredentialIDs("EVCS")));
                identifiers.addAll(Arrays.asList(api.getCredentialIDs("OVCS")));
                if (identifiers.isEmpty()) throw new IllegalStateException();
                String selected = null;
                CredentialInfo selectedInfo = null;
                String expected = required("EXPECTED_CERT_SHA256");
                if (!expected.matches("[A-Fa-f0-9]{64}")) {
                    throw new IllegalArgumentException();
                }
                for (String identifier : identifiers) {
                    failureStage = "credential-inspection";
                    CredentialInfo info = api.getCredentialInfo(identifier);
                    X509Certificate certificate = info.getCerts().get(0);
                    String fingerprint = digest(certificate, "SHA-256");
                    if (fingerprint.equalsIgnoreCase(expected)) {
                        if (selected != null) throw new IllegalStateException();
                        certificate.checkValidity();
                        if (!certificate.getExtendedKeyUsage().contains("1.3.6.1.5.5.7.3.3")) {
                            throw new IllegalStateException();
                        }
                        if (args[0].equals("sign")
                            && !digest(certificate, "SHA-1").equalsIgnoreCase(required("EXPECTED_CERT_SHA1"))) {
                            throw new IllegalStateException();
                        }
                        if (!new X500Principal(required("EXPECTED_CERT_SUBJECT")).equals(
                            certificate.getSubjectX500Principal())) throw new IllegalStateException();
                        selected = identifier;
                        selectedInfo = info;
                    }
                }
                if (args[0].equals("inspect")) {
                    failureStage = "certificate-export";
                    if (selectedInfo == null || selectedInfo.getCerts().isEmpty()) throw new IllegalStateException();
                    Path certificateOutput = Path.of(required("CERTIFICATE_OUTPUT")).toRealPath();
                    if (!Files.isDirectory(certificateOutput)) throw new IllegalStateException();
                    try (Stream<Path> existing = Files.list(certificateOutput)) {
                        if (existing.findAny().isPresent()) throw new IllegalStateException();
                    }
                    for (int index = 0; index < selectedInfo.getCerts().size(); index++) {
                        X509Certificate certificate = selectedInfo.getCerts().get(index);
                        Files.write(certificateOutput.resolve("chain-" + index + ".der"), certificate.getEncoded());
                        report.println("Public certificate chain " + index + " subject: "
                            + certificate.getSubjectX500Principal().getName());
                        report.println("Public certificate chain " + index + " issuer: "
                            + certificate.getIssuerX500Principal().getName());
                        report.println("Public certificate chain " + index + " validity: "
                            + certificate.getNotBefore().toInstant() + " to " + certificate.getNotAfter().toInstant());
                        report.println("Public certificate chain " + index + " SHA256: " + digest(certificate, "SHA-256"));
                        report.println("Public certificate chain " + index + " SHA1: " + digest(certificate, "SHA-1"));
                    }
                    report.println("Public certificate inspection complete. Signatures requested: 0.");
                    result = 0;
                } else {
                    failureStage = "signing";
                    if (selected == null || api.isOtpTypeOnline(selected)) throw new IllegalStateException();
                    String seed = required("ES_TOTP_SECRET");
                    byte[] decoded = Base64.getDecoder().decode(seed);
                    if (decoded.length < 16 || decoded.length > 64) throw new IllegalArgumentException();
                    Arrays.fill(decoded, (byte) 0);
                    Path input = Path.of(required("SIGNING_INPUT")).toRealPath();
                    // Picocli receives Java strings in-process. No vendor batch file or child process runs.
                    int code = new CommandLine(new CodeSignTool()).execute("sign",
                        "-username=" + username, "-password=" + password,
                        "-credential_id=" + selected, "-totp_secret=" + seed,
                        "-input_file_path=" + input, "-output_dir_path=" + Path.of(required("SIGNING_OUTPUT")).toRealPath(),
                        "-malware_block=true");
                    report.println("Vendor signing exit code: " + code + ". No retry performed.");
                    result = code == 0 ? 0 : 71;
                }
            }
        } catch (Throwable failure) {
            // Never print exception text, causes, HTTP bodies, or a stack trace.
            report.println("Signing stopped at safe stage " + failureStage
                + ". Authentication, certificate, configuration or vendor check failed. No retry performed.");
        }
        System.exit(result);
    }
}
