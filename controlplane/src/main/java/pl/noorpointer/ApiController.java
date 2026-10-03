package pl.noorpointer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
class ApiController {
    record TextDocument(@NotBlank @Size(max=1_000_000) String document) {}
    private final PolicyService policies;
    private final AuditService audit;
    private final SignatureService signatures;
    private final Documents documents;
    private final boolean demoEnabled;

    ApiController(PolicyService policies, AuditService audit, SignatureService signatures, Documents documents,
            @Value("${control-plane.demo-enabled}") boolean demoEnabled) {
        this.policies=policies;this.audit=audit;this.signatures=signatures;this.documents=documents;this.demoEnabled=demoEnabled;
    }

    @GetMapping("/policies") List<PolicyService.Revision> policies() {return policies.list();}
    @GetMapping("/policies/active") Map<String,Object> active() {return policies.active();}
    @GetMapping("/policies/{id}") PolicyService.Revision policy(@PathVariable long id) {return policies.get(id);}
    @PostMapping("/policies") @ResponseStatus(HttpStatus.CREATED)
    PolicyService.Revision create(@Valid @RequestBody PolicyService.Draft draft) {return policies.create(draft);}
    @PostMapping("/policies/validate") Map<String,Object> validate(@Valid @RequestBody TextDocument body) {
        documents.validate("policy",documents.parse(body.document()));return Map.of("valid",true);
    }
    @PostMapping("/policies/{id}/publish") Map<String,Object> publish(@PathVariable long id) {return policies.publish(id);}
    @GetMapping("/profiles/{name}") JsonNode profile(@PathVariable String name) {return documents.profile(name);}
    @GetMapping("/contracts/{name}") JsonNode contract(@PathVariable String name) {return documents.schema(name);}
    @GetMapping("/gateway/policy") ResponseEntity<?> gatewayPolicy(@RequestHeader(value="If-None-Match",required=false) String previous) {
        return cached(policies.gatewayPolicy(),previous);
    }
    @GetMapping("/gateway/signatures") ResponseEntity<?> gatewaySignatures(@RequestHeader(value="If-None-Match",required=false) String previous) {
        return cached(signatures.feed(),previous);
    }
    @PostMapping("/gateway/events") Map<String,Object> ingest(@RequestBody JsonNode event) {return audit.ingest(event);}
    @GetMapping("/signatures") Map<String,Object> feed() {return signatures.feed();}
    @PostMapping("/signatures/import") Map<String,Object> importFeed(@Valid @RequestBody TextDocument body) {return signatures.replace(body.document());}
    @GetMapping("/events/{id}") JsonNode event(@PathVariable String id) {return audit.get(id);}
    @GetMapping("/events") Map<String,Object> events(
        @RequestParam(required=false) String action, @RequestParam(required=false) String category,
        @RequestParam(required=false) String agent, @RequestParam(required=false) Instant from,
        @RequestParam(required=false) Instant to, @RequestParam(defaultValue="0") int page,
        @RequestParam(defaultValue="20") int size) {
        return audit.list(new AuditService.Filter(action,category,agent,from,to),page,size);
    }
    @GetMapping("/dashboard") Map<String,Object> dashboard() {
        var policy = policies.gatewayPolicy();
        long enabled = 0, total = 0;
        for (JsonNode control : policy.path("controls")) {total++;if(control.path("enabled").asBoolean())enabled++;}
        return Map.of("summary",audit.summary(),"budgets",audit.budgets(policy),"active_policy",policies.active(),
            "controls_enabled",enabled,"controls_total",total,"demo_enabled",demoEnabled);
    }
    @GetMapping({"/events/export", "/v1/audit/export"}) ResponseEntity<?> export(
        @RequestParam(defaultValue="json") String format, @RequestParam(required=false) String action,
        @RequestParam(required=false) String category, @RequestParam(required=false) String agent,
        @RequestParam(required=false) Instant from, @RequestParam(required=false) Instant to) {
        if (!List.of("json","csv","cef").contains(format)) throw new IllegalArgumentException("Supported formats: json, csv, cef");
        var events = audit.export(new AuditService.Filter(action,category,agent,from,to));
        String body;
        String type;
        if(format.equals("json")) {body=documents.write(events);type="application/json";}
        else if(format.equals("csv")) {
            type="text/csv;charset=UTF-8";
            var fields=List.of("id","occurred_at","agent_id","team","model","kind","action","severity","control","category","signature_id","tokens","cost_usd","message");
            var text=new StringBuilder(String.join(",",fields)).append('\n');
            for(JsonNode event:events) text.append(fields.stream().map(f->csv(event.path(f).asText())).collect(java.util.stream.Collectors.joining(","))).append('\n');
            body=text.toString();
        } else {
            type="text/plain;charset=UTF-8";
            var text=new StringBuilder();
            for(JsonNode event:events) text.append("CEF:0|NoorPointer|ControlPlane|0.1|").append(cefHeader(event.path("control").asText()))
                .append('|').append(cefHeader(event.path("action").asText())).append('|').append(severity(event.path("severity").asText()))
                .append("|externalId=").append(cefValue(event.path("id").asText())).append(" rt=").append(Instant.parse(event.path("occurred_at").asText()).toEpochMilli())
                .append(" suser=").append(cefValue(event.path("agent_id").asText())).append(" cat=").append(cefValue(event.path("category").asText()))
                .append(" msg=").append(cefValue(event.path("message").asText())).append('\n');
            body=text.toString();
        }
        return ResponseEntity.ok().header("Content-Type",type).header("Content-Disposition","attachment; filename=\"noorpointer-events."+format+"\"").body(body);
    }

    @PostMapping("/demo/events") Map<String,Object> demo() {
        if(!demoEnabled) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Demo is disabled");
        String[] actions={"allow","block","allow","redact","block","allow"};
        String[] controls={"model_allowlist","prompt_injection","model_allowlist","pii_regex","secrets","mcp_tools"};
        String[] categories={"unclassified","LLM01:2025","unclassified","LLM02:2025","LLM02:2025","unclassified"};
        long version=((PolicyService.Revision)policies.active().get("revision")).version();
        int count=0;
        for(int i=0;i<18;i++) {
            int index=i%actions.length;
            Instant time=Instant.now().minusSeconds((i%7)*86400L+60L*i);
            String request=UUID.randomUUID().toString();
            ObjectNode event=(ObjectNode)documents.read("{}");
            event.put("id",UUID.randomUUID().toString());event.put("occurred_at",time.toString());event.put("kind","decision");
            event.put("request_id",request);event.put("agent_id",i%2==0?"finance-agent":"research-agent");event.put("team",i%2==0?"finance":"research");
            event.put("model","llama3.1:8b");event.put("action",actions[index]);event.put("control",controls[index]);
            event.put("category",categories[index]);event.put("severity",actions[index].equals("block")?"high":"info");
            event.put("policy_version",version);event.put("latency_ms",3+index*2);
            event.put("message","Synthetic demo event: "+controls[index]);event.set("context",documents.read("{\"demo\":true}"));
            audit.ingest(event);count++;
            if(!actions[index].equals("block")) {
                event.put("id",UUID.randomUUID().toString());event.put("kind","usage");event.put("action","allow");event.put("tokens",400+i*10);
                event.put("cost_usd",0.004);event.put("gpu_seconds",0.5);event.put("control","usage");event.put("message","Synthetic usage report");
                audit.ingest(event);count++;
            }
        }
        return Map.of("created",count,"synthetic",true);
    }

    private ResponseEntity<?> cached(Object value,String previous) {
        try {
            String tag="\""+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(documents.write(value).getBytes(StandardCharsets.UTF_8)))+"\"";
            if (previous != null && java.util.Arrays.stream(previous.split(",")).map(String::trim).anyMatch(t -> t.equals(tag) || t.equals("W/"+tag) || t.equals("*"))) {
                return ResponseEntity.status(HttpStatus.NOT_MODIFIED).eTag(tag).build();
            }
            return ResponseEntity.ok().eTag(tag).header("Cache-Control","private, no-cache").body(value);
        } catch(java.security.NoSuchAlgorithmException e) {throw new IllegalStateException(e);}
    }
    static String csv(String value) {
        if(value.matches("(?s)^\\s*[=+@-].*"))value="'"+value;
        return "\""+value.replace("\"","\"\"")+"\"";
    }
    private static String cefHeader(String value) {return value.replace("\\","\\\\").replace("|","\\|").replace("\n"," ").replace("\r"," ");}
    private static String cefValue(String value) {return value.replace("\\","\\\\").replace("=","\\=").replace("\n","\\n").replace("\r","\\r");}
    private static int severity(String level) {return switch(level){case "critical"->10;case "high"->8;case "medium"->5;case "low"->3;default->1;};}
}
