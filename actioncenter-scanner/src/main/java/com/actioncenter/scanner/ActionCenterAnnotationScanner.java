package com.actioncenter.scanner;

import com.actioncenter.annotations.ActionCenterField;
import com.actioncenter.annotations.ActionCenterModel;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.type.TypeMirror;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.StandardLocation;
import java.io.IOException;
import java.io.Writer;
import java.util.*;

/**
 * ActionCenterAnnotationScanner — Compile-Time APT Processor
 *
 * <p>Automatically invoked by {@code javac} when teams include the
 * {@code actioncenter-scanner} JAR as a {@code provided} dependency.
 * Scans all classes annotated with {@link ActionCenterModel}, extracts
 * metadata from their {@link ActionCenterField}-annotated fields, and
 * writes {@code target/actioncenter/action-center-catalog.json}.</p>
 *
 * <p>Teams do not need to invoke this manually — it fires on every
 * {@code mvn compile} or {@code gradle compileJava}.</p>
 */
@SupportedAnnotationTypes({
    "com.actioncenter.annotations.ActionCenterModel",
    "com.actioncenter.annotations.ActionCenterField"
})
@SupportedSourceVersion(SourceVersion.RELEASE_11)
public class ActionCenterAnnotationScanner extends AbstractProcessor {

    private static final String OUTPUT_FOLDER   = "actioncenter";
    private static final String OUTPUT_FILENAME = "action-center-catalog.json";

    private final List<Map<String, Object>> eventCatalog = new ArrayList<>();
    private final ObjectMapper objectMapper = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT);

    // -----------------------------------------------------------------------
    // Main processing entry point
    // -----------------------------------------------------------------------

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            // Final round — write the accumulated catalog to disk
            writeCatalog();
            return false;
        }

        // Scan every class annotated with @ActionCenterModel
        for (Element element : roundEnv.getElementsAnnotatedWith(ActionCenterModel.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.WARNING,
                    "@ActionCenterModel should only be placed on classes",
                    element
                );
                continue;
            }

            TypeElement classElement = (TypeElement) element;
            Map<String, Object> eventEntry = buildEventEntry(classElement);
            eventCatalog.add(eventEntry);

            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "[ActionCenterScanner] Registered event model: "
                    + classElement.getQualifiedName()
            );
        }

        return true;
    }

    // -----------------------------------------------------------------------
    // Build a single event entry map from a @ActionCenterModel class
    // -----------------------------------------------------------------------

    private Map<String, Object> buildEventEntry(TypeElement classElement) {
        ActionCenterModel modelAnnotation = classElement.getAnnotation(ActionCenterModel.class);

        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("className",    classElement.getQualifiedName().toString());
        entry.put("simpleName",   classElement.getSimpleName().toString());
        entry.put("name",         modelAnnotation.name());
        entry.put("domain",       modelAnnotation.domain());
        entry.put("version",      modelAnnotation.version());
        entry.put("description",  modelAnnotation.description());
        entry.put("tags",         Arrays.asList(modelAnnotation.tags()));
        entry.put("fields",       buildFieldEntries(classElement));

        return entry;
    }

    // -----------------------------------------------------------------------
    // Walk fields — collect those annotated with @ActionCenterField
    // -----------------------------------------------------------------------

    private List<Map<String, Object>> buildFieldEntries(TypeElement classElement) {
        List<Map<String, Object>> fields = new ArrayList<>();

        for (Element enclosed : classElement.getEnclosedElements()) {
            if (enclosed.getKind() != ElementKind.FIELD) continue;

            VariableElement fieldElement = (VariableElement) enclosed;
            ActionCenterField fieldAnnotation = fieldElement.getAnnotation(ActionCenterField.class);

            // Include ALL fields; mark annotated ones with richer metadata
            Map<String, Object> fieldEntry = new LinkedHashMap<>();
            fieldEntry.put("name",      fieldElement.getSimpleName().toString());
            fieldEntry.put("type",      getSimpleTypeName(fieldElement.asType()));
            fieldEntry.put("fullType",  fieldElement.asType().toString());

            if (fieldAnnotation != null) {
                fieldEntry.put("description", fieldAnnotation.description());
                fieldEntry.put("required",    fieldAnnotation.required());
                fieldEntry.put("sensitive",   fieldAnnotation.sensitive());
                fieldEntry.put("example",     fieldAnnotation.example());
                fieldEntry.put("annotated",   true);
            } else {
                fieldEntry.put("annotated", false);
            }

            fields.add(fieldEntry);
        }

        return fields;
    }

    // -----------------------------------------------------------------------
    // Write the final JSON catalog
    // -----------------------------------------------------------------------

    private void writeCatalog() {
        if (eventCatalog.isEmpty()) {
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "[ActionCenterScanner] No @ActionCenterModel classes found. Skipping catalog generation."
            );
            return;
        }

        Map<String, Object> root = new LinkedHashMap<>();
        root.put("generatedBy",  "ActionCenterAnnotationScannerAgent");
        root.put("generatedAt",  java.time.Instant.now().toString());
        root.put("totalEvents",  eventCatalog.size());
        root.put("events",       eventCatalog);

        try {
            FileObject resource = processingEnv.getFiler().createResource(
                StandardLocation.CLASS_OUTPUT,
                "",
                OUTPUT_FOLDER + "/" + OUTPUT_FILENAME
            );

            try (Writer writer = resource.openWriter()) {
                writer.write(objectMapper.writeValueAsString(root));
            }

            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "[ActionCenterScanner] Generated catalog → "
                    + OUTPUT_FOLDER + "/" + OUTPUT_FILENAME
                    + "  (" + eventCatalog.size() + " events)"
            );

        } catch (IOException e) {
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                "[ActionCenterScanner] Failed to write catalog: " + e.getMessage()
            );
        }
    }

    // -----------------------------------------------------------------------
    // Utility: extract simple type name from TypeMirror
    // -----------------------------------------------------------------------

    private String getSimpleTypeName(TypeMirror typeMirror) {
        String fullType = typeMirror.toString();
        // Strip package prefix for readability (e.g. java.lang.String → String)
        int lastDot = fullType.lastIndexOf('.');
        return lastDot >= 0 ? fullType.substring(lastDot + 1) : fullType;
    }
}
