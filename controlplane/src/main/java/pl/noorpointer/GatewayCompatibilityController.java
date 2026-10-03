package pl.noorpointer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

/** Bridges the repository's initial Go audit format to the Java event contract. */
@RestController
@RequestMapping("/api/v1")
class GatewayCompatibilityController {
    private final AuditService audit;
    private final PolicyService policies;
    private final Documents documents;

    GatewayCompatibilityController(AuditService audit, PolicyService policies, Documents documents) {
        this.audit=audit;this.policies=policies;this.documents=documents;
    }

    @GetMapping("/policies")
    JsonNode policy() {return policies.gatewayPolicy();}

    @PostMapping("/audit/events")
    Map<String,Object> ingest(@RequestBody JsonNode input) {
        if (!input.isObject()) throw new IllegalArgumentException("Expected an audit event object");
        String action=switch(input.path("action").asText().toLowerCase(Locale.ROOT)) {
            case "allowed","allow"->"allow";case "blocked","block"->"block";
            case "redacted","redact"->"redact";case "monitor"->"monitor";case "timeout"->"timeout";
            default->throw new IllegalArgumentException("Unknown gateway audit action");
        };
        String request=input.path("request_id").asText(UUID.randomUUID().toString());
        String id=UUID.nameUUIDFromBytes(request.getBytes(StandardCharsets.UTF_8)).toString();
        String reason=input.path("reason").asText("GATEWAY_DECISION");
        ObjectNode event=(ObjectNode)documents.read("{}");
        event.put("id",id+"-decision");event.put("request_id",request);
        event.put("occurred_at",input.path("timestamp").asText(Instant.now().toString()));
        event.put("kind","decision");event.put("agent_id",input.path("agent_id").asText(""));
        event.put("team",input.path("team").asText("unknown"));event.put("model",input.path("model").asText("unknown"));
        event.put("action",action);event.put("message",reason);
        event.put("severity",action.equals("block")?"high":"info");
        event.put("category",input.path("owasp_category").asText("unclassified"));
        event.put("control",switch(reason) {
            case "PROMPT_INJECTION_DETECTED"->"prompt_injection";case "SECRET_LEAKAGE_DETECTED"->"secrets";
            case "PII_ANONYMIZED","PII_DETECTED"->"pii_regex";case "LOOP_BREAKER_TRIGGERED"->"agent_loops";
            case "HISTORICAL_EXPLOIT_SIGNATURE_MATCHED"->"attack_signatures";case "BUDGET_EXCEEDED"->"budgets";
            default->"gateway";
        });
        // The initial gateway sends unredacted prompts for some blocked events. Keep metadata only.
        if (input.path("details").isObject()) event.set("context",input.get("details"));
        if (input.has("policy_version")) event.set("policy_version",input.get("policy_version"));
        documents.validate("audit",event);
        ObjectNode usage=null;
        if (input.has("token_usage")) {
            JsonNode reported=input.path("token_usage");
            if (!reported.isObject()) throw new IllegalArgumentException("token_usage must be an object");
            if (reported.has("cost_usd") && !reported.path("cost_usd").isNumber()) {
                throw new IllegalArgumentException("cost_usd must be a number");
            }
            long tokens;
            try {tokens=Math.addExact(nonnegativeLong(reported,"prompt_tokens"),nonnegativeLong(reported,"completion_tokens"));}
            catch(ArithmeticException e){throw new IllegalArgumentException("Token total is too large");}
            usage=event.deepCopy();usage.put("id",id+"-usage");usage.put("kind","usage");usage.put("control","usage");
            usage.put("tokens",tokens);usage.put("cost_usd",reported.has("cost_usd")?reported.path("cost_usd").decimalValue():BigDecimal.ZERO);
            documents.validate("audit",usage);
        }
        var result=audit.ingest(event);
        if (usage!=null) audit.ingest(usage);
        return result;
    }

    private long nonnegativeLong(JsonNode node,String field) {
        if(!node.has(field))return 0;
        if(!node.path(field).isIntegralNumber() || !node.path(field).canConvertToLong() || node.path(field).asLong()<0) {
            throw new IllegalArgumentException(field+" must be a nonnegative integer");
        }
        return node.path(field).asLong();
    }
}
