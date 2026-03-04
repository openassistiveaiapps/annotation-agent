package com.actioncenter.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a field within an {@link ActionCenterModel}-annotated class as an
 * event-relevant field that should be included in the generated event catalog.
 *
 * <h3>Example usage:</h3>
 * <pre>{@code
 * @ActionCenterModel(name = "UserRegistered", domain = "auth")
 * public class UserRegisteredEvent {
 *
 *     @ActionCenterField(description = "Unique user identifier", required = true)
 *     private String userId;
 *
 *     @ActionCenterField(description = "User email", sensitive = true, required = true)
 *     private String email;
 *
 *     @ActionCenterField(description = "Timestamp of registration")
 *     private LocalDateTime registeredAt;
 * }
 * }</pre>
 *
 * <p><strong>Note:</strong> SOURCE-retained — no runtime overhead.</p>
 */
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.FIELD)
public @interface ActionCenterField {

    /**
     * Human-readable description of what this field represents in the event context.
     */
    String description() default "";

    /**
     * Whether this field is mandatory for the event to be considered valid.
     */
    boolean required() default false;

    /**
     * Marks this field as containing sensitive/PII data.
     * The scanner will flag these in the catalog for compliance awareness.
     */
    boolean sensitive() default false;

    /**
     * Optional example value for documentation purposes.
     */
    String example() default "";
}
