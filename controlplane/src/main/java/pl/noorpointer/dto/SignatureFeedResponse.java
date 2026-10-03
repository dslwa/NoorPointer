package pl.noorpointer.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;

public record SignatureFeedResponse(List<JsonNode> signatures) {}
