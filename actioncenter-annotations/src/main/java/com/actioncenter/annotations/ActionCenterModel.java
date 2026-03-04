package com.actioncenter.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a class as an ActionCenter event model.
 *
 * <p>Place this annotation on model/event/DTO classes that represent
 * domain events consumed or produced by the ActionCenter system.
 * The {@link com.actioncenter.scanner.ActionCenterAnnotationScanner}
 * will read these at compile time and generate an event catalog JSON.</p>
 *
 * <h3>Example usage:</h3>
 * <pre>{@code
 * @ActionCenterModel(
 *     name        = "UserRegistered",
 *     domain      = "auth",
 *     version     = "1.0",
 *     description = "Fired when a new user completes registration",
 *     tags        = {"user", "onboarding"}
 * )
 * public class UserRegisteredEvent {
 *
 *     @ActionCenterField(description = "Unique user identifier", required = true)
 *     private String userId;
 *
 *     @ActionCenterField(description = "User email address", sensitive = true)
 *     private String email;
 * }
 * }</pre>
 *
 * <p><strong>Note:</strong> This annotation is SOURCE-retained and has
 * zero runtime overhead. It is stripped by the compiler after processing.</p>
 */
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface ActionCenterModel {

    /**
     * The logical event name.
     * Convention: PascalCase verb-noun (e.g. "UserRegistered", "OrderShipped").
     */
    String name();

    /**
     * The bounded domain this event belongs to (e.g. "auth", "payments", "notifications").
     * Defaults to empty string if not specified.
     */
    String domain() default "";

    /**
     * Semantic version of this event schema. Increment when fields change.
     */
    String version() default "1.0";

    /**
     * Human-readable description of when and why this event is raised.
     */
    String description() default "";

    /**
     * Optional tags for grouping, filtering, or documentation purposes.
     */
    String[] tags() default {};
}
